import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import {
    AlertTriangle,
    Archive,
    Check,
    CheckCheck,
    Lock,
    LucideAngularModule,
    LucideIconData,
    RefreshCw,
    ShieldAlert,
    ShieldCheck,
    ShieldOff,
    Trash2,
} from 'lucide-angular';

import { DirectoryService } from '../../../core/services/directory.service';
import { DecryptedMessage, DecryptStatus } from '../../../core/services/message.service';
import { AvatarComponent } from '../../../shared/ui/avatar/avatar.component';
import { messageTime } from '../../../shared/utils/display';

/**
 * How a status renders.
 *
 * Every `DecryptStatus` gets its own treatment, because collapsing them makes the interface lie
 * about the guarantee — see `docs/ui-states.md`. In particular:
 *
 *   `no_key`      is transient and normal, so it must not look like an error.
 *   `unverified`  decrypted but unauthenticated: the content may be forged, so it must not look
 *                 like ordinary text.
 *   `failed`      could be tampering, so it must not look like a blank message.
 *   `legacy`      is permanently unreadable, so it must not look like loading.
 *   `plaintext`   carries no confidentiality, so it must not show a lock.
 */
interface StatusView {
    /** Body text when the message itself has none. */
    placeholder: string | null;
    detail: string | null;
    tone: 'normal' | 'pending' | 'warn' | 'danger' | 'inert';
    icon: LucideIconData | null;
}

const STATUS_VIEWS: Record<DecryptStatus, StatusView> = {
    ok: { placeholder: null, detail: null, tone: 'normal', icon: null },
    plaintext: { placeholder: null, detail: null, tone: 'normal', icon: null },
    no_key: {
        placeholder: 'Waiting for this sender’s key',
        detail: 'They have not wrapped their chain for your device yet. This usually resolves on its own.',
        tone: 'pending',
        icon: Lock,
    },
    unverified: {
        placeholder: null,
        detail: 'Signature did not verify — this content may have been forged.',
        tone: 'warn',
        icon: ShieldAlert,
    },
    failed: {
        placeholder: 'Could not be decrypted',
        detail: 'Tampering, a consumed chain index, or a stale grant. The original content is not recoverable here.',
        tone: 'danger',
        icon: AlertTriangle,
    },
    legacy: {
        placeholder: 'Permanently unreadable',
        detail: 'Encrypted with the pre-migration scheme. There is no key that can open it.',
        tone: 'inert',
        icon: Archive,
    },
};

@Component({
    selector: 'app-message-bubble',
    imports: [LucideAngularModule, AvatarComponent],
    templateUrl: './message-bubble.component.html',
    styleUrl: './message-bubble.component.scss',
    changeDetection: ChangeDetectionStrategy.OnPush,
    host: {
        '[class.is-outgoing]': 'isOwn()',
        // An attribute rather than a `[class]` string: a class-map binding competes with the
        // `[class.is-outgoing]` binding for the same property, and the tone styles need both to be
        // reliably present at once.
        '[attr.data-tone]': 'view().tone',
    },
})
export class MessageBubbleComponent {
    private readonly directory = inject(DirectoryService);

    readonly message = input.required<DecryptedMessage>();
    /** Groups and channels label each sender; a two-party chat does not need to. */
    readonly showSender = input(true);
    readonly canDelete = input(false);

    readonly deleteRequested = output<string>();

    readonly isOwn = computed(() => this.directory.isMe(this.message().senderId));
    readonly sender = computed(() => this.directory.lookup(this.message().senderId));
    readonly view = computed(() => STATUS_VIEWS[this.message().status]);
    readonly time = computed(() => messageTime(this.message().createdAt));

    /** Only ever true when a signature was actually checked and passed — never a default. */
    readonly showVerified = computed(() => this.message().senderVerified && this.message().status === 'ok');

    /** A channel post is signed but not confidential, so it gets the opposite of a lock. */
    readonly showBroadcastMark = computed(() => this.message().status === 'plaintext');

    readonly checkIcon = Check;
    readonly checkCheckIcon = CheckCheck;
    readonly refreshIcon = RefreshCw;
    readonly shieldCheckIcon = ShieldCheck;
    readonly shieldOffIcon = ShieldOff;
    readonly trashIcon = Trash2;
}
