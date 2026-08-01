import { HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { v4 as uuidv4 } from 'uuid';

import { signChannelPost, verifyChannelPost } from '../crypto/channel';
import { openMessage, sealMessage } from '../crypto/envelope';
import { b64uDecode, fromUtf8, utf8 } from '../crypto/primitives';
import { ChatKeys, MessageResponse } from '../models/crypto.model';
import { ChatApiService } from './chat-api.service';
import { CryptoApiService } from './crypto-api.service';
import { isCryptoNotEnabled } from './crypto-errors';
import { KeyStoreService } from './key-store.service';

/** How a message rendered out — the UI needs to distinguish these, not just show text or nothing. */
export type DecryptStatus =
    | 'ok'
    | 'no_key' // we hold no grant for this sender's chain yet
    | 'unverified' // decrypted, but the signature did not verify
    | 'failed' // decryption failed outright
    | 'plaintext' // legacy unencrypted, or a channel post
    | 'legacy'; // pre-migration RSA content we cannot read

export interface DecryptedMessage {
    id: string;
    chatId: string;
    senderId: string;
    createdAt: string;
    text: string | null;
    status: DecryptStatus;
    isEdited: boolean;
    /** True only when a signature was checked and passed. */
    senderVerified: boolean;
}

/** A page of history, ciphertext included so undecryptable entries can be retried in place. */
export interface LoadedMessages {
    raw: MessageResponse[];
    messages: DecryptedMessage[];
}

@Injectable({ providedIn: 'root' })
export class MessageService {
    private readonly chatApi = inject(ChatApiService);
    private readonly cryptoApi = inject(CryptoApiService);
    private readonly keyStore = inject(KeyStoreService);

    /**
     * Encrypt and send.
     *
     * On EPOCH_STALE the chat re-keyed between composing and sending — usually because someone
     * left. The old ciphertext must not be retried as-is: it is bound to the previous epoch and
     * would be readable by whoever just departed. So we discard the cached chain, mint a fresh one
     * for the new epoch, and re-encrypt from plaintext.
     */
    async sendText(chatId: string, text: string, replyTo?: string): Promise<MessageResponse> {
        const keys = await firstValueFrom(this.cryptoApi.getChatKeys(chatId));

        try {
            return await this.sealAndSend(chatId, keys.current_epoch, text, replyTo);
        } catch (error) {
            if (!this.isEpochStale(error)) {
                throw error;
            }

            const currentEpoch =
                this.epochFromError(error) ?? (await firstValueFrom(this.cryptoApi.getChatKeys(chatId))).current_epoch;

            this.keyStore.invalidateSenderChain(chatId, keys.current_epoch);
            return this.sealAndSend(chatId, currentEpoch, text, replyTo);
        }
    }

    private async sealAndSend(chatId: string, epoch: number, text: string, replyTo?: string): Promise<MessageResponse> {
        const identity = this.keyStore.currentIdentity;
        if (!identity) {
            throw new Error('key store is locked');
        }

        const own = await this.keyStore.ensureSenderChain(chatId, epoch);
        const { key, nonce, index } = own.chain.nextMessageKey();

        const envelope = await sealMessage({
            messageKey: key,
            nonce,
            signingPrivate: own.chainSigningPrivate,
            chatId,
            epoch,
            senderId: identity.userId,
            senderKeyId: own.senderKeyId,
            chainIndex: index,
            plaintext: utf8(text),
        });

        return firstValueFrom(this.chatApi.sendEnvelope(chatId, envelope, replyTo));
    }

    /** Post to a channel: signed with the identity key, not encrypted. */
    async sendChannelPost(chatId: string, content: string): Promise<MessageResponse> {
        const identity = this.keyStore.currentIdentity;
        if (!identity) {
            throw new Error('key store is locked');
        }

        const postId = uuidv4();

        return firstValueFrom(
            this.chatApi.sendChannelPost(chatId, {
                v: 1,
                alg: 'ed25519-post-v1',
                post_id: postId,
                content,
                sig: signChannelPost({
                    signingPrivate: identity.signingPrivate,
                    chatId,
                    senderId: identity.userId,
                    postId,
                    content,
                }),
            })
        );
    }

    /**
     * Fetch and decrypt a chat's history.
     *
     * Grants are ingested first so chains exist before we walk the messages; otherwise every
     * message from a sender we have not seen would report no_key on first load.
     */
    async loadMessages(chatId: string, limit = 50, beforeId?: string): Promise<LoadedMessages> {
        // A chat need not have crypto settings at all: channels are signed rather than encrypted, and
        // a private chat has none until encryption is enabled for it. Neither is an error — there are
        // simply no grants to ingest, and `decrypt` reports anything it cannot open as `no_key`
        // rather than pretending to have read it.
        const keys = await this.tryGetChatKeys(chatId);
        if (keys) {
            await this.keyStore.ingestDistributions(chatId, keys.distributions);
        }

        const raw = await firstValueFrom(this.chatApi.getMessages(chatId, limit, beforeId));

        // The ciphertext is handed back too. A message that decrypts to no_key today may be
        // decryptable in a second, and re-running it needs the envelope, not another round trip.
        return { raw, messages: await Promise.all(raw.map((message) => this.decrypt(chatId, message))) };
    }

    /**
     * Re-fetch this chat's distributions and ingest any we do not already hold.
     *
     * The cure for `no_key`. A sender mints a new chain whenever their in-memory state is gone —
     * after a reload, or when an epoch opens — and publishes it as a new distribution. Until we
     * fetch that distribution we hold no chain for the `skid` their messages carry, so they decrypt
     * to `no_key`. Nothing arrives over the socket to tell us; the grants have to be pulled.
     */
    async refreshGrants(chatId: string): Promise<void> {
        const keys = await this.tryGetChatKeys(chatId);
        if (keys) {
            await this.keyStore.ingestDistributions(chatId, keys.distributions);
        }
    }

    /** Chat keys, or null when the chat has no crypto settings. Other failures still throw. */
    private async tryGetChatKeys(chatId: string): Promise<ChatKeys | null> {
        try {
            return await firstValueFrom(this.cryptoApi.getChatKeys(chatId));
        } catch (error) {
            if (isCryptoNotEnabled(error)) {
                return null;
            }
            throw error;
        }
    }

    async decrypt(chatId: string, message: MessageResponse): Promise<DecryptedMessage> {
        const base = {
            id: message._id,
            chatId: message.chat_id,
            senderId: message.sender_id,
            createdAt: message.created_at,
            isEdited: message.is_edited,
        };

        if (message.content_format === 'channel_signed_v1' && message.channel_post) {
            // Readable by design. What matters is whether the author is who the post claims.
            const senderKeys = await firstValueFrom(this.cryptoApi.getKeysBatch([message.sender_id]));
            const verified =
                senderKeys.length > 0 &&
                verifyChannelPost({
                    signingPublic: b64uDecode(senderKeys[0].signing_public_key),
                    signature: message.channel_post.sig,
                    chatId,
                    senderId: message.sender_id,
                    postId: message.channel_post.post_id,
                    content: message.channel_post.content,
                });

            return {
                ...base,
                text: message.channel_post.content,
                status: 'plaintext',
                senderVerified: verified,
            };
        }

        if (message.content_format === 'legacy_plaintext') {
            return { ...base, text: message.encrypted_content, status: 'plaintext', senderVerified: false };
        }

        if (message.content_format === 'legacy_rsa') {
            return { ...base, text: null, status: 'legacy', senderVerified: false };
        }

        const envelope = message.envelope;
        if (!envelope) {
            return { ...base, text: null, status: 'failed', senderVerified: false };
        }

        const chain = this.keyStore.getReceiverChain(chatId, envelope.epoch, envelope.skid);
        if (!chain) {
            // Not a failure: the sender simply has not wrapped their chain for us yet.
            return { ...base, text: null, status: 'no_key', senderVerified: false };
        }

        const signingPublic = this.keyStore.getChainSigningKey(envelope.skid);

        try {
            const messageKey = chain.messageKeyFor(envelope.idx);
            const plaintext = await openMessage({
                messageKey: messageKey.key,
                envelope,
                chatId,
                senderId: message.sender_id,
                signingPublic,
            });

            return { ...base, text: fromUtf8(plaintext), status: 'ok', senderVerified: Boolean(signingPublic) };
        } catch {
            // Could be a consumed index, a stale grant, or genuine tampering. The UI must not
            // present any of those as ordinary text.
            return { ...base, text: null, status: 'failed', senderVerified: false };
        }
    }

    private isEpochStale(error: unknown): boolean {
        return error instanceof HttpErrorResponse && error.status === 409 && error.error?.error_code === 'EPOCH_STALE';
    }

    private epochFromError(error: unknown): number | null {
        if (error instanceof HttpErrorResponse) {
            const current = error.error?.details?.current_epoch;
            return typeof current === 'number' ? current : null;
        }
        return null;
    }
}
