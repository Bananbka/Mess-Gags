import { HttpErrorResponse } from '@angular/common/http';
import { computed, effect, inject, Injectable, signal, untracked } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { Chat } from '../models/chat.model';
import { ChatKeys, MessageResponse } from '../models/crypto.model';
import { ChatApiService } from './chat-api.service';
import { CryptoApiService } from './crypto-api.service';
import { isAlreadyEnabled, isCryptoNotEnabled, isEncryptionRefused } from './crypto-errors';
import { DirectoryService } from './directory.service';
import { DecryptedMessage, MessageService } from './message.service';
import { SessionService } from './session.service';
import { WebSocketService } from './websocket.service';

const PAGE_SIZE = 50;

/** A message we are sending. Kept out of the decrypted history until the server accepts it. */
export interface PendingMessage {
    localId: string;
    text: string;
    status: 'sending' | 'failed';
    /** True when the failure survived the automatic EPOCH_STALE re-encrypt-and-retry. */
    rekeyFailure: boolean;
}

/**
 * What the message list renders, in order.
 *
 * The dividers are items rather than flags because they belong at a position in the history, not at
 * the top of the pane — the encryption boundary in particular sits between two real messages.
 */
export type ConversationItem =
    | { kind: 'history-floor' }
    | { kind: 'encryption-boundary' }
    | { kind: 'message'; message: DecryptedMessage }
    | { kind: 'pending'; pending: PendingMessage };

/** A sidebar preview. `readable` is false whenever we are not entitled or not yet able to read it. */
export interface ChatPreview {
    text: string;
    readable: boolean;
}

/**
 * The conversation state the UI reads.
 *
 * Most of this service exists to keep the states in `docs/ui-states.md` distinguishable. The
 * temptation in a messenger store is to reduce everything to a list of strings plus an error flag;
 * doing that here would make the interface claim guarantees the protocol does not provide.
 */
@Injectable({ providedIn: 'root' })
export class ChatStoreService {
    private readonly chatApi = inject(ChatApiService);
    private readonly cryptoApi = inject(CryptoApiService);
    private readonly messages_ = inject(MessageService);
    private readonly directory = inject(DirectoryService);
    private readonly session = inject(SessionService);
    private readonly ws = inject(WebSocketService);

    readonly chats = signal<Chat[]>([]);
    readonly chatsLoading = signal(false);
    readonly chatsError = signal<string | null>(null);

    readonly activeChatId = signal<string | null>(null);
    readonly activeChat = computed(() => this.chats().find((c) => c.id === this.activeChatId()) ?? null);

    readonly messages = signal<DecryptedMessage[]>([]);
    readonly pending = signal<PendingMessage[]>([]);
    readonly messagesLoading = signal(false);
    readonly hasMoreHistory = signal(false);

    readonly chatKeys = signal<ChatKeys | null>(null);

    /**
     * The client recomputed `member_set_hash` from the roster and it disagreed with the epoch
     * commitment. The server may have inserted a device that would receive future messages, so key
     * distribution is refused and sending is blocked. This is the highest-severity state in the app.
     */
    readonly memberVerificationError = signal<string | null>(null);

    /**
     * Encryption could not be enabled for this chat — the group exceeds the member ceiling that
     * sender-key distribution can carry, or the server refused for another permanent reason.
     *
     * Its own state rather than a generic error: the chat is readable and its history is intact, but
     * nothing new can be sealed. Sending is blocked instead of falling back to plaintext, because a
     * chat the user believes is encrypted must never quietly stop being so.
     */
    readonly encryptionUnavailable = signal<string | null>(null);

    /** A new epoch opened — membership changed and chains are being re-minted. Transient. */
    readonly isRekeying = signal(false);

    readonly typingUserIds = signal<string[]>([]);
    readonly onlineUserIds = signal<string[]>([]);

    readonly isOnline = this.ws.isConnected;

    /**
     * Sending is impossible while the member set is in doubt, or while there is no key to seal with.
     * Refusing in both cases is the whole point.
     */
    readonly canSend = computed(() => this.memberVerificationError() === null && this.encryptionUnavailable() === null);

    /** Why sending is blocked, if it is. Ordered by severity. */
    readonly sendBlockedReason = computed<string | null>(() => {
        if (this.memberVerificationError()) {
            return 'Blocked: the member set for this chat could not be verified.';
        }
        if (this.encryptionUnavailable()) {
            return this.encryptionUnavailable();
        }
        return null;
    });

    /**
     * Previews for chats we have opened this session, keyed by chat id.
     *
     * Only these can be shown as text. Decrypting every chat's newest message on list load would
     * mean one grant-ingestion round trip per chat, so an unopened chat honestly reports that its
     * preview is sealed rather than rendering a blank line.
     */
    private readonly previewOverrides = signal(new Map<string, ChatPreview>());

    /**
     * The history floor.
     *
     * `history_visibility: 'joined'` means the server withheld pre-join ciphertext outright — not
     * just the keys — so that sender, timing, size and reply structure cannot leak. It is permanent,
     * and it is only shown once we have actually paged back to the start of what we can see.
     */
    readonly hasHistoryFloor = computed(() => {
        const keys = this.chatKeys();
        if (!keys || keys.history_visibility !== 'joined' || keys.my_join_epoch === null) {
            return false;
        }
        return keys.epochs.some((epoch) => epoch.epoch < keys.my_join_epoch!);
    });

    readonly conversation = computed<ConversationItem[]>(() => {
        const messages = this.messages();
        const isChannel = this.activeChat()?.chat_type === 'channel';
        const items: ConversationItem[] = [];

        if (this.hasHistoryFloor() && !this.hasMoreHistory()) {
            items.push({ kind: 'history-floor' });
        }

        // Group history from before encryption was switched on stays plaintext forever; it is never
        // retroactively sealed. The boundary marks where the guarantee actually begins.
        let boundaryEmitted = isChannel;
        let sawUnencrypted = false;

        for (const message of messages) {
            const unencrypted = message.status === 'plaintext' || message.status === 'legacy';

            if (!boundaryEmitted && sawUnencrypted && !unencrypted) {
                items.push({ kind: 'encryption-boundary' });
                boundaryEmitted = true;
            }

            sawUnencrypted ||= unencrypted;
            items.push({ kind: 'message', message });
        }

        for (const pending of this.pending()) {
            items.push({ kind: 'pending', pending });
        }

        return items;
    });

    private rekeyTimer: ReturnType<typeof setTimeout> | null = null;
    private wsBound = false;

    constructor() {
        // Reloading on chat change keeps the component free of imperative fetch orchestration.
        effect(() => {
            const chatId = this.activeChatId();
            untracked(() => {
                if (chatId) {
                    void this.openChat(chatId);
                } else {
                    this.resetConversation();
                }
            });
        });
    }

    /** Subscribe to the realtime stream once. Safe to call from every shell instantiation. */
    bindRealtime(): void {
        if (this.wsBound) {
            return;
        }
        this.wsBound = true;

        this.ws.messages.subscribe((event) => {
            switch (event.event_type) {
                case 'new_message':
                    void this.onIncomingMessage(event.chat_id, event.payload);
                    break;
                case 'message_deleted':
                    this.onMessageDeleted(event.payload);
                    break;
                case 'key_epoch_started':
                    this.onEpochStarted(event.chat_id);
                    break;
                case 'typing_start':
                    this.setTyping(event.chat_id, event.user_id, true);
                    break;
                case 'typing_stop':
                    this.setTyping(event.chat_id, event.user_id, false);
                    break;
                case 'user_online':
                    this.setPresence(event.user_id, true);
                    break;
                case 'user_offline':
                    this.setPresence(event.user_id, false);
                    break;
                case 'chat_created':
                    void this.loadChats();
                    break;
            }
        });
    }

    async loadChats(): Promise<void> {
        this.chatsLoading.set(true);
        this.chatsError.set(null);

        try {
            const chats = await firstValueFrom(this.chatApi.getChats());
            this.chats.set(chats);
            this.warmDirectoryFromChats(chats);
        } catch {
            this.chatsError.set('Could not load your chats.');
        } finally {
            this.chatsLoading.set(false);
        }
    }

    /**
     * A private chat's title is its counterpart's display name, so the chat list doubles as the only
     * id-keyed name source for DM peers.
     */
    private warmDirectoryFromChats(chats: Chat[]): void {
        const me = this.session.user()?.id;

        for (const chat of chats) {
            if (chat.chat_type !== 'private') {
                continue;
            }
            const peer = chat.participants.find((p) => p.user_id !== me);
            if (peer) {
                this.directory.rememberPrivateChatPeer(peer.user_id, chat.title, chat.avatar_url);
            }
        }
    }

    private resetConversation(): void {
        this.messages.set([]);
        this.pending.set([]);
        this.chatKeys.set(null);
        this.encryptionUnavailable.set(null);
        this.memberVerificationError.set(null);
        this.typingUserIds.set([]);
        this.hasMoreHistory.set(false);
    }

    private async openChat(chatId: string): Promise<void> {
        this.resetConversation();
        this.messagesLoading.set(true);

        try {
            // Channels are signed rather than encrypted, so they have no epochs, no roster and no
            // grants. Asking for their keys always 404s.
            if (!(await this.isChannel(chatId))) {
                // Fetched before the history so the roster and grants are in place; otherwise every
                // message from a sender we have not ingested yet would report no_key on first paint.
                this.chatKeys.set(await this.ensureEncryptionEnabled(chatId));
            }

            const decrypted = await this.messages_.loadMessages(chatId, PAGE_SIZE);
            this.messages.set(decrypted);
            this.hasMoreHistory.set(decrypted.length === PAGE_SIZE);
            this.cachePreview(chatId, decrypted);

            await this.markRead(chatId, decrypted);
        } catch {
            this.messages.set([]);
        } finally {
            this.messagesLoading.set(false);
        }
    }

    /**
     * Is this a channel? Answered from the loaded list, falling back to a fetch on a deep link.
     *
     * Worth a round trip when the list has not arrived yet: the answer decides whether this chat is
     * supposed to be encrypted at all, and guessing wrong either hides a real problem or invents one.
     */
    private async isChannel(chatId: string): Promise<boolean> {
        const known = this.chats().find((c) => c.id === chatId);
        if (known) {
            return known.chat_type === 'channel';
        }

        try {
            return (await firstValueFrom(this.chatApi.getChat(chatId))).chat_type === 'channel';
        } catch {
            return false;
        }
    }

    /**
     * Fetch the chat's keys, turning encryption on first if it has never been enabled.
     *
     * `POST /chats/private` and `POST /chats/group` do not create a `ChatCryptoSettings` row, so a
     * brand-new chat has no epoch and `GET .../keys` answers 404 CRYPTO_NOT_ENABLED. Enabling on
     * first open is what makes a private chat encrypted from its first message without requiring the
     * creator to have done anything special.
     *
     * A refusal — too many members — is recorded rather than swallowed. Sending stays blocked, which
     * is correct: quietly falling back to plaintext in a chat the user believes is encrypted is the
     * worst outcome available.
     */
    private async ensureEncryptionEnabled(chatId: string): Promise<ChatKeys | null> {
        try {
            return await firstValueFrom(this.cryptoApi.getChatKeys(chatId));
        } catch (error) {
            if (!isCryptoNotEnabled(error)) {
                throw error;
            }
        }

        try {
            await firstValueFrom(this.cryptoApi.enableEncryption(chatId));
        } catch (error) {
            // A race with another device is fine — the row we wanted now exists either way.
            if (!isAlreadyEnabled(error)) {
                const refusal = isEncryptionRefused(error);
                this.encryptionUnavailable.set(refusal ?? 'Could not enable encryption for this chat.');
                return null;
            }
        }

        return firstValueFrom(this.cryptoApi.getChatKeys(chatId));
    }

    /** Page backwards. ObjectId monotonicity is the ordering key, so the oldest id is the cursor. */
    async loadOlder(): Promise<void> {
        const chatId = this.activeChatId();
        const oldest = this.messages()[0];

        if (!chatId || !oldest || this.messagesLoading()) {
            return;
        }

        this.messagesLoading.set(true);
        try {
            const older = await this.messages_.loadMessages(chatId, PAGE_SIZE, oldest.id);
            this.messages.update((current) => [...older, ...current]);
            this.hasMoreHistory.set(older.length === PAGE_SIZE);
        } finally {
            this.messagesLoading.set(false);
        }
    }

    /**
     * Send, tracking the outcome as its own state.
     *
     * `MessageService.sendText` already re-encrypts and retries once on EPOCH_STALE — that path is
     * invisible on purpose. Only a failure that survives the retry surfaces, which is what
     * `docs/ui-states.md` asks for.
     */
    async send(text: string): Promise<void> {
        const chatId = this.activeChatId();
        const chat = this.activeChat();
        if (!chatId || !chat || !text.trim()) {
            return;
        }

        const localId = `local-${crypto.randomUUID()}`;
        this.pending.update((p) => [...p, { localId, text, status: 'sending', rekeyFailure: false }]);

        try {
            const sent =
                chat.chat_type === 'channel'
                    ? await this.messages_.sendChannelPost(chatId, text)
                    : await this.messages_.sendText(chatId, text);

            this.pending.update((p) => p.filter((item) => item.localId !== localId));
            this.appendDecrypted(await this.messages_.decrypt(chatId, sent));
            this.bumpChatPreview(chatId, sent);
        } catch (error) {
            if (this.isMemberVerificationFailure(error)) {
                // Blocking, not retryable: we refused to hand keys to a roster we cannot verify.
                this.memberVerificationError.set((error as Error).message);
                this.pending.update((p) => p.filter((item) => item.localId !== localId));
                return;
            }

            this.pending.update((p) =>
                p.map((item) =>
                    item.localId === localId
                        ? { ...item, status: 'failed' as const, rekeyFailure: this.looksLikeRekey(error) }
                        : item
                )
            );
        }
    }

    async retry(localId: string): Promise<void> {
        const item = this.pending().find((p) => p.localId === localId);
        if (!item) {
            return;
        }

        this.pending.update((p) => p.filter((entry) => entry.localId !== localId));
        await this.send(item.text);
    }

    discardPending(localId: string): void {
        this.pending.update((p) => p.filter((entry) => entry.localId !== localId));
    }

    async deleteMessage(messageId: string): Promise<void> {
        await firstValueFrom(this.chatApi.deleteMessage(messageId));
        this.messages.update((list) => list.filter((m) => m.id !== messageId));
    }

    /** Retry key ingestion for a chat — the usual cure for a screen full of `no_key`. */
    async refreshKeys(): Promise<void> {
        const chatId = this.activeChatId();
        if (!chatId) {
            return;
        }

        this.memberVerificationError.set(null);
        await this.openChat(chatId);
    }

    /**
     * The one-line summary in the chat list.
     *
     * Under E2E a preview is only available when we hold the sender's chain, which in practice means
     * the chat has been opened. Saying so is the point: a blank row would read as "no messages".
     */
    preview(chat: Chat): ChatPreview {
        const override = this.previewOverrides().get(chat.id);
        if (override) {
            return override;
        }

        const last = chat.last_message;
        if (!last) {
            return { text: 'No messages yet', readable: true };
        }

        switch (last.content_format) {
            case 'channel_signed_v1':
                // Readable by design — channels are signed, not encrypted.
                return { text: last.channel_post?.content ?? '', readable: true };
            case 'legacy_plaintext':
                return { text: last.encrypted_content ?? '', readable: true };
            case 'legacy_rsa':
                return { text: 'Unreadable legacy message', readable: false };
            default:
                return { text: 'Encrypted message', readable: false };
        }
    }

    private cachePreview(chatId: string, decrypted: DecryptedMessage[]): void {
        const newest = decrypted.at(-1);
        if (!newest) {
            return;
        }

        this.previewOverrides.update((map) => {
            const next = new Map(map);
            next.set(chatId, {
                text: newest.text ?? this.unreadableLabel(newest),
                readable: newest.text !== null,
            });
            return next;
        });
    }

    private unreadableLabel(message: DecryptedMessage): string {
        switch (message.status) {
            case 'no_key':
                return 'Waiting for keys';
            case 'legacy':
                return 'Unreadable legacy message';
            case 'failed':
                return 'Could not be decrypted';
            default:
                return 'Encrypted message';
        }
    }

    sendTyping(typing: boolean): void {
        const chatId = this.activeChatId();
        if (chatId) {
            this.ws.sendTyping(chatId, typing);
        }
    }

    private async markRead(chatId: string, decrypted: DecryptedMessage[]): Promise<void> {
        const newest = decrypted.at(-1);
        if (!newest) {
            return;
        }

        this.ws.sendRead(chatId, newest.id);
        this.chats.update((list) => list.map((c) => (c.id === chatId ? { ...c, unread_count: 0 } : c)));
    }

    private async onIncomingMessage(chatId: string | null, payload: Record<string, unknown>): Promise<void> {
        const raw = payload as unknown as MessageResponse;
        if (!chatId || !raw?._id) {
            return;
        }

        this.bumpChatPreview(chatId, raw);

        if (chatId !== this.activeChatId()) {
            this.chats.update((list) =>
                list.map((c) => (c.id === chatId ? { ...c, unread_count: c.unread_count + 1 } : c))
            );
            return;
        }

        this.appendDecrypted(await this.messages_.decrypt(chatId, raw));
        this.ws.sendRead(chatId, raw._id);
    }

    private appendDecrypted(message: DecryptedMessage): void {
        this.messages.update((list) => (list.some((m) => m.id === message.id) ? list : [...list, message]));
        this.cachePreview(message.chatId, [message]);
    }

    private onMessageDeleted(payload: Record<string, unknown>): void {
        const id = payload['message_id'];
        if (typeof id === 'string') {
            this.messages.update((list) => list.filter((m) => m.id !== id));
        }
    }

    /**
     * A membership change opened a new epoch.
     *
     * The chat is re-keyed by re-reading its keys: our cached sender chain belongs to the closed
     * epoch, and the server will reject anything sealed under it.
     */
    private onEpochStarted(chatId: string | null): void {
        if (!chatId || chatId !== this.activeChatId()) {
            return;
        }

        this.isRekeying.set(true);
        void this.refreshKeys().finally(() => {
            if (this.rekeyTimer) {
                clearTimeout(this.rekeyTimer);
            }
            // Held briefly so the notice is legible rather than a flicker.
            this.rekeyTimer = setTimeout(() => this.isRekeying.set(false), 1500);
        });
    }

    private setTyping(chatId: string | null, userId: string | null, typing: boolean): void {
        if (!userId || chatId !== this.activeChatId()) {
            return;
        }

        this.typingUserIds.update((ids) => {
            const without = ids.filter((id) => id !== userId);
            return typing ? [...without, userId] : without;
        });
    }

    private setPresence(userId: string | null, online: boolean): void {
        if (!userId) {
            return;
        }

        this.onlineUserIds.update((ids) => {
            const without = ids.filter((id) => id !== userId);
            return online ? [...without, userId] : without;
        });
    }

    private bumpChatPreview(chatId: string, raw: MessageResponse): void {
        this.chats.update((list) => {
            const index = list.findIndex((c) => c.id === chatId);
            if (index < 0) {
                return list;
            }

            const updated = { ...list[index], last_message: raw, updated_at: raw.created_at };
            return [updated, ...list.slice(0, index), ...list.slice(index + 1)];
        });
    }

    private isMemberVerificationFailure(error: unknown): boolean {
        return error instanceof Error && error.message.startsWith('Member set verification failed');
    }

    private looksLikeRekey(error: unknown): boolean {
        // MessageService already re-encrypted and retried once, so an epoch error reaching here
        // means the chat re-keyed twice mid-send. That is the one case worth surfacing.
        return error instanceof HttpErrorResponse && error.status === 409 && error.error?.error_code === 'EPOCH_STALE';
    }
}
