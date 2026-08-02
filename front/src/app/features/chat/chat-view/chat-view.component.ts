import {
    AfterViewChecked,
    ChangeDetectionStrategy,
    Component,
    computed,
    effect,
    ElementRef,
    inject,
    input,
    signal,
    viewChild,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import {
    AlertTriangle,
    ArrowLeft,
    Info,
    LucideAngularModule,
    MessageSquare,
    RefreshCw,
    Shield,
    ShieldAlert,
    ShieldOff,
    SkipForward,
    Users,
    X,
} from 'lucide-angular';

import { ChatStoreService, ConversationItem, PendingMessage } from '../../../core/services/chat-store.service';
import { DirectoryService } from '../../../core/services/directory.service';
import { DecryptedMessage } from '../../../core/services/message.service';
import { SessionService } from '../../../core/services/session.service';
import { AvatarComponent } from '../../../shared/ui/avatar/avatar.component';
import { ComposerComponent } from '../composer/composer.component';
import { MessageBubbleComponent } from '../message-bubble/message-bubble.component';

@Component({
    selector: 'app-chat-view',
    imports: [RouterLink, LucideAngularModule, AvatarComponent, MessageBubbleComponent, ComposerComponent],
    templateUrl: './chat-view.component.html',
    styleUrl: './chat-view.component.scss',
    changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChatViewComponent implements AfterViewChecked {
    private readonly store = inject(ChatStoreService);
    private readonly directory = inject(DirectoryService);
    private readonly session = inject(SessionService);
    private readonly router = inject(Router);

    /** Bound from the `:chatId` route parameter. */
    readonly chatId = input<string | undefined>(undefined);

    readonly chat = this.store.activeChat;
    readonly conversation = this.store.conversation;
    readonly loading = this.store.messagesLoading;
    readonly hasMoreHistory = this.store.hasMoreHistory;
    readonly isRekeying = this.store.isRekeying;
    readonly canSend = this.store.canSend;
    readonly memberVerificationError = this.store.memberVerificationError;
    readonly encryptionUnavailable = this.store.encryptionUnavailable;
    readonly sendBlockedReason = this.store.sendBlockedReason;

    readonly bannerDismissed = signal(false);

    readonly isChannel = computed(() => this.chat()?.chat_type === 'channel');
    readonly isGroupLike = computed(() => this.chat()?.chat_type !== 'private');

    readonly title = computed(() => {
        const chat = this.chat();
        if (!chat) {
            return '';
        }
        return chat.title ?? (chat.chat_type === 'channel' ? 'Channel' : 'Untitled chat');
    });

    readonly subtitle = computed(() => {
        const chat = this.chat();
        if (!chat) {
            return '';
        }

        const typing = this.store.typingUserIds();
        if (typing.length === 1) {
            return `${this.directory.lookup(typing[0]).name} is typing…`;
        }
        if (typing.length > 1) {
            return `${typing.length} people are typing…`;
        }

        if (chat.chat_type === 'private') {
            const peer = chat.participants.find((p) => p.user_id !== this.session.user()?.id);
            return peer && this.store.onlineUserIds().includes(peer.user_id) ? 'Online' : 'Last seen recently';
        }

        const count = chat.participants.length;
        if (chat.chat_type === 'channel') {
            return count ? `${count} subscribers` : 'Channel';
        }
        return count ? `${count} members` : 'Group';
    });

    readonly peerId = computed(() => {
        const chat = this.chat();
        if (chat?.chat_type !== 'private') {
            return null;
        }
        return chat.participants.find((p) => p.user_id !== this.session.user()?.id)?.user_id ?? null;
    });

    /** Channels are never end-to-end encrypted, so nothing about them may imply confidentiality. */
    readonly showChannelNotice = this.isChannel;

    private readonly scroller = viewChild<ElementRef<HTMLElement>>('scroller');
    private pinToBottom = true;
    private lastItemCount = 0;

    readonly arrowLeftIcon = ArrowLeft;
    readonly infoIcon = Info;
    readonly shieldIcon = Shield;
    readonly shieldAlertIcon = ShieldAlert;
    readonly shieldOffIcon = ShieldOff;
    readonly skipForwardIcon = SkipForward;
    readonly refreshIcon = RefreshCw;
    readonly alertIcon = AlertTriangle;
    readonly usersIcon = Users;
    readonly messageSquareIcon = MessageSquare;
    readonly closeIcon = X;

    constructor() {
        effect(() => {
            const id = this.chatId() ?? null;
            this.store.activeChatId.set(id);
            this.bannerDismissed.set(false);
            this.pinToBottom = true;
            // Force the next check to count as a change, so switching to a chat that happens to have
            // the same number of rows still scrolls to its newest message.
            this.lastItemCount = -1;
        });
    }

    /**
     * A stable identity per row.
     *
     * Index tracking would recycle a bubble onto a different message whenever older history is
     * prepended, which matters now that a bubble carries its own state — its `no_key` grace timer
     * would end up attached to the wrong message.
     */
    /**
     * Present an unsent message in the same shape a delivered one has.
     *
     * We wrote it, so its content is known and its authorship is not in question — status `ok` and
     * `senderVerified` are statements of fact here, not claims about a signature we checked.
     */
    pendingAsMessage(pending: PendingMessage): DecryptedMessage {
        return {
            id: pending.localId,
            chatId: this.chat()?.id ?? '',
            senderId: this.session.user()?.id ?? '',
            createdAt: pending.createdAt,
            text: pending.text,
            status: 'ok',
            isEdited: false,
            senderVerified: true,
        };
    }

    itemKey(item: ConversationItem, index: number): string {
        switch (item.kind) {
            case 'message':
                return `m:${item.message.id}`;
            case 'pending':
                return `p:${item.pending.localId}`;
            default:
                return `${item.kind}:${index}`;
        }
    }

    ngAfterViewChecked(): void {
        // Bail before touching the counter when there is nothing to scroll yet. The pane lives inside
        // an @if on the loaded chat, so the first few checks run without it — and recording the count
        // then would consume the one transition that triggers the scroll, leaving a freshly opened
        // conversation sitting at the top of its history.
        const element = this.scroller()?.nativeElement;
        if (!element) {
            return;
        }

        const count = this.conversation().length;
        if (count === this.lastItemCount) {
            return;
        }

        this.lastItemCount = count;
        if (this.pinToBottom) {
            // After layout, not during this check: scrollHeight is not final until the new rows have
            // been laid out, and fonts settling can change it again.
            requestAnimationFrame(() => this.scrollToBottom());
        }
    }

    /** Loading older pages must not yank the view; only stay pinned if the user already is. */
    onScroll(): void {
        const element = this.scroller()?.nativeElement;
        if (!element) {
            return;
        }

        this.pinToBottom = element.scrollHeight - element.scrollTop - element.clientHeight < 80;

        if (element.scrollTop < 120 && this.hasMoreHistory() && !this.loading()) {
            const before = element.scrollHeight;
            void this.store.loadOlder().then(() => {
                const after = this.scroller()?.nativeElement;
                if (after) {
                    after.scrollTop += after.scrollHeight - before;
                }
            });
        }
    }

    private scrollToBottom(): void {
        const element = this.scroller()?.nativeElement;
        if (element) {
            element.scrollTop = element.scrollHeight;
        }
    }

    async send(text: string): Promise<void> {
        this.pinToBottom = true;
        await this.store.send(text);
    }

    onTyping(active: boolean): void {
        this.store.sendTyping(active);
    }

    retry(localId: string): void {
        void this.store.retry(localId);
    }

    discard(localId: string): void {
        this.store.discardPending(localId);
    }

    refreshKeys(): void {
        void this.store.refreshKeys();
    }

    async deleteMessage(messageId: string): Promise<void> {
        await this.store.deleteMessage(messageId);
    }

    canDelete(senderId: string): boolean {
        return this.directory.isMe(senderId);
    }

    async openSafetyNumber(): Promise<void> {
        const chat = this.chat();
        const peer = this.peerId();
        if (chat && peer) {
            await this.router.navigate(['/chats', chat.id, 'safety', peer]);
        }
    }

    async backToList(): Promise<void> {
        await this.router.navigate(['/chats']);
    }
}
