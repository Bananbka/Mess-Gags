import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import {
    ArrowLeft,
    ChevronRight,
    LogOut,
    LucideAngularModule,
    Shield,
    ShieldAlert,
    ShieldCheck,
    ShieldOff,
    Trash2,
    UserMinus,
} from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { computeMemberSetHash } from '../../../core/crypto/grants';
import { Chat, ParticipantRole } from '../../../core/models/chat.model';
import { ChatRoster } from '../../../core/models/crypto.model';
import { ChatApiService } from '../../../core/services/chat-api.service';
import { ChatStoreService } from '../../../core/services/chat-store.service';
import { CryptoApiService } from '../../../core/services/crypto-api.service';
import { DirectoryService } from '../../../core/services/directory.service';
import { SessionService } from '../../../core/services/session.service';
import { AvatarComponent } from '../../../shared/ui/avatar/avatar.component';
import { safetyNumberGroups } from '../../../shared/utils/display';

interface MemberRow {
    userId: string;
    name: string;
    username: string | null;
    avatarUrl: string | null;
    resolved: boolean;
    role: ParticipantRole | null;
    isMe: boolean;
    /** True when the roster publishes an identity key for this member's device. */
    hasKeys: boolean;
}

@Component({
    selector: 'app-chat-info',
    imports: [RouterLink, LucideAngularModule, AvatarComponent],
    templateUrl: './chat-info.component.html',
    styleUrl: './chat-info.component.scss',
    changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChatInfoComponent {
    private readonly chatApi = inject(ChatApiService);
    private readonly cryptoApi = inject(CryptoApiService);
    private readonly directory = inject(DirectoryService);
    private readonly session = inject(SessionService);
    private readonly store = inject(ChatStoreService);
    private readonly router = inject(Router);

    readonly chatId = input.required<string>();

    readonly chat = signal<Chat | null>(null);
    readonly roster = signal<ChatRoster | null>(null);
    readonly safetyNumber = signal<string | null>(null);
    readonly loading = signal(true);
    readonly error = signal<string | null>(null);
    readonly busy = signal(false);

    /**
     * The anti-ghost check, run here as well as before key distribution.
     *
     * `member_set_hash` is recomputed from the roster the server just handed us and compared with the
     * commitment recorded for the epoch. A mismatch means the server may have inserted a device that
     * would receive future messages. The backend stores the hash but cannot enforce this — only the
     * client can, so it is surfaced on the screen where the roster is shown.
     */
    readonly memberSetVerified = computed(() => {
        const roster = this.roster();
        if (!roster) {
            return null;
        }
        return computeMemberSetHash(roster.members.map((m) => m.device_id)) === roster.member_set_hash;
    });

    readonly isPrivate = computed(() => this.chat()?.chat_type === 'private');
    readonly isChannel = computed(() => this.chat()?.chat_type === 'channel');

    readonly title = computed(() => {
        const chat = this.chat();
        if (!chat) {
            return '';
        }
        return chat.title ?? (chat.chat_type === 'channel' ? 'Channel' : 'Untitled chat');
    });

    readonly members = computed<MemberRow[]>(() => {
        const chat = this.chat();
        const roster = this.roster();
        if (!chat) {
            return [];
        }

        const keyed = new Set(roster?.members.map((m) => m.user_id) ?? []);
        const me = this.session.user()?.id;

        return chat.participants.map((participant) => {
            const identity = this.directory.lookup(participant.user_id);
            return {
                userId: participant.user_id,
                name: identity.name,
                username: identity.username,
                avatarUrl: identity.avatarUrl,
                resolved: identity.resolved,
                role: participant.role,
                isMe: participant.user_id === me,
                hasKeys: keyed.has(participant.user_id),
            };
        });
    });

    readonly peerId = computed(() => this.members().find((m) => !m.isMe)?.userId ?? null);
    readonly membersWithoutKeys = computed(() => this.members().filter((m) => !m.hasKeys).length);
    readonly safetyPreview = computed(() => safetyNumberGroups(this.safetyNumber() ?? '').slice(0, 3));

    /** Only an owner or admin may change membership; the API rejects a member outright. */
    readonly canManage = computed(() => {
        const me = this.members().find((m) => m.isMe);
        return me?.role === 'owner' || me?.role === 'admin';
    });

    readonly arrowLeftIcon = ArrowLeft;
    readonly chevronRightIcon = ChevronRight;
    readonly shieldIcon = Shield;
    readonly shieldCheckIcon = ShieldCheck;
    readonly shieldAlertIcon = ShieldAlert;
    readonly shieldOffIcon = ShieldOff;
    readonly logOutIcon = LogOut;
    readonly trashIcon = Trash2;
    readonly userMinusIcon = UserMinus;

    constructor() {
        effect(() => void this.load(this.chatId()));
    }

    private async load(chatId: string): Promise<void> {
        this.loading.set(true);
        this.error.set(null);

        try {
            // `GET /chats/{id}` is the only endpoint that populates participants — the list endpoint
            // returns plain dicts with no participants key at all.
            const chat = await firstValueFrom(this.chatApi.getChat(chatId));
            this.chat.set(chat);

            if (chat.chat_type !== 'channel') {
                try {
                    this.roster.set(await firstValueFrom(this.cryptoApi.getRoster(chatId)));
                } catch {
                    this.roster.set(null);
                }
            }

            const peer = chat.participants.find((p) => p.user_id !== this.session.user()?.id);
            if (chat.chat_type === 'private' && peer) {
                try {
                    this.safetyNumber.set(await firstValueFrom(this.cryptoApi.getSafetyNumber(peer.user_id)));
                } catch {
                    this.safetyNumber.set(null);
                }
            }
        } catch {
            this.error.set('Could not load this chat.');
        } finally {
            this.loading.set(false);
        }
    }

    async removeMember(userId: string): Promise<void> {
        this.busy.set(true);
        try {
            await firstValueFrom(this.chatApi.removeParticipants(this.chatId(), [userId]));
            await this.load(this.chatId());
            await this.store.loadChats();
        } catch {
            this.error.set('Could not remove that member.');
        } finally {
            this.busy.set(false);
        }
    }

    async leave(): Promise<void> {
        this.busy.set(true);
        try {
            await firstValueFrom(this.chatApi.leaveChat(this.chatId()));
            this.store.activeChatId.set(null);
            await this.store.loadChats();
            await this.router.navigate(['/chats']);
        } catch {
            this.error.set('Could not leave this chat.');
        } finally {
            this.busy.set(false);
        }
    }

    async back(): Promise<void> {
        await this.router.navigate(['/chats', this.chatId()]);
    }
}
