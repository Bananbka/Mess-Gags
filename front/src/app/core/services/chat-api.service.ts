import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { map, Observable } from 'rxjs';

import { MessageEnvelope } from '../crypto/envelope';
import { SuccessResponse } from '../models/api.model';
import { Chat, UserSearchResult } from '../models/chat.model';
import { ChannelPostPayload, MessageResponse } from '../models/crypto.model';
import { ConfigService } from './config.service';

@Injectable({ providedIn: 'root' })
export class ChatApiService {
    private readonly http = inject(HttpClient);
    private readonly configService = inject(ConfigService);

    private get chatsUrl(): string {
        return this.configService.apiUrl + 'chats/';
    }

    private get messagesUrl(): string {
        return this.configService.apiUrl + 'messages/';
    }

    getChats(): Observable<Chat[]> {
        return this.http.get<SuccessResponse<Chat[]>>(this.chatsUrl).pipe(map((r) => r.data));
    }

    getChat(chatId: string): Observable<Chat> {
        return this.http.get<SuccessResponse<Chat>>(`${this.chatsUrl}${chatId}`).pipe(map((r) => r.data));
    }

    createPrivateChat(targetUserId: string): Observable<Chat> {
        return this.http
            .post<SuccessResponse<Chat>>(`${this.chatsUrl}private`, { target_user_id: targetUserId })
            .pipe(map((r) => r.data));
    }

    createGroupChat(title: string, description: string, participantIds: string[]): Observable<Chat> {
        return this.http
            .post<SuccessResponse<Chat>>(`${this.chatsUrl}group`, {
                title,
                description,
                participant_ids: participantIds,
            })
            .pipe(map((r) => r.data));
    }

    createChannel(title: string, description: string, subscriberIds: string[]): Observable<Chat> {
        return this.http
            .post<SuccessResponse<Chat>>(`${this.chatsUrl}channel`, {
                title,
                description,
                subscriber_ids: subscriberIds,
            })
            .pipe(map((r) => r.data));
    }

    leaveChat(chatId: string): Observable<unknown> {
        return this.http.post<SuccessResponse<unknown>>(`${this.chatsUrl}${chatId}/leave`, {}).pipe(map((r) => r.data));
    }

    addParticipants(chatId: string, userIds: string[]): Observable<Chat> {
        return this.http
            .post<SuccessResponse<Chat>>(`${this.chatsUrl}${chatId}/add-participants`, { user_ids: userIds })
            .pipe(map((r) => r.data));
    }

    removeParticipants(chatId: string, userIds: string[]): Observable<Chat> {
        return this.http
            .post<SuccessResponse<Chat>>(`${this.chatsUrl}${chatId}/delete-participants`, { user_ids: userIds })
            .pipe(map((r) => r.data));
    }

    getMessages(chatId: string, limit = 50, beforeId?: string): Observable<MessageResponse[]> {
        let params = new HttpParams().set('limit', limit);
        if (beforeId) {
            params = params.set('before_id', beforeId);
        }

        return this.http
            .get<SuccessResponse<MessageResponse[]>>(`${this.chatsUrl}${chatId}/messages`, { params })
            .pipe(map((r) => r.data));
    }

    /** Send a sealed message into an encrypted chat. */
    sendEnvelope(chatId: string, envelope: MessageEnvelope, replyTo?: string): Observable<MessageResponse> {
        return this.http
            .post<SuccessResponse<MessageResponse>>(this.messagesUrl, {
                chat_id: chatId,
                envelope,
                reply_to_message_id: replyTo ?? null,
            })
            .pipe(map((r) => r.data));
    }

    /** Send a signed broadcast post. Channels are authenticated but not confidential. */
    sendChannelPost(chatId: string, post: ChannelPostPayload): Observable<MessageResponse> {
        return this.http
            .post<SuccessResponse<MessageResponse>>(this.messagesUrl, { chat_id: chatId, channel_post: post })
            .pipe(map((r) => r.data));
    }

    deleteMessage(messageId: string): Observable<unknown> {
        return this.http.delete<SuccessResponse<unknown>>(`${this.messagesUrl}${messageId}`).pipe(map((r) => r.data));
    }

    searchUsers(query: string, limit = 10): Observable<UserSearchResult[]> {
        return this.http
            .get<SuccessResponse<UserSearchResult[]>>(`${this.configService.apiUrl}users/search`, {
                params: new HttpParams().set('query', query).set('limit', limit),
            })
            .pipe(map((r) => r.data));
    }
}
