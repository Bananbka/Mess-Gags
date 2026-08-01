import { ChangeDetectionStrategy, Component, ElementRef, input, output, signal, viewChild } from '@angular/core';
import { LucideAngularModule, Paperclip, RefreshCw, Send, ShieldAlert } from 'lucide-angular';

@Component({
    selector: 'app-composer',
    imports: [LucideAngularModule],
    templateUrl: './composer.component.html',
    styleUrl: './composer.component.scss',
    changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ComposerComponent {
    /** False while the member set cannot be verified — sending is refused, not merely discouraged. */
    readonly canSend = input(true);
    readonly blockedReason = input<string | null>(null);
    readonly rekeying = input(false);
    readonly placeholder = input('Message…');

    readonly submitted = output<string>();
    readonly typing = output<boolean>();

    readonly text = signal('');

    private readonly area = viewChild<ElementRef<HTMLTextAreaElement>>('area');
    private typingActive = false;
    private typingTimer: ReturnType<typeof setTimeout> | null = null;

    readonly sendIcon = Send;
    readonly paperclipIcon = Paperclip;
    readonly refreshIcon = RefreshCw;
    readonly shieldAlertIcon = ShieldAlert;

    onInput(value: string): void {
        this.text.set(value);
        this.autoGrow();
        this.pingTyping();
    }

    onKeydown(event: KeyboardEvent): void {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            this.send();
        }
    }

    send(): void {
        const value = this.text().trim();
        if (!value || !this.canSend()) {
            return;
        }

        this.submitted.emit(value);
        this.text.set('');
        this.stopTyping();

        const element = this.area()?.nativeElement;
        if (element) {
            element.value = '';
            element.style.height = 'auto';
        }
    }

    private autoGrow(): void {
        const element = this.area()?.nativeElement;
        if (!element) {
            return;
        }

        element.style.height = 'auto';
        element.style.height = `${Math.min(element.scrollHeight, 160)}px`;
    }

    /** Debounced so a fast typist emits one start and one stop, not one event per keystroke. */
    private pingTyping(): void {
        if (!this.typingActive) {
            this.typingActive = true;
            this.typing.emit(true);
        }

        if (this.typingTimer) {
            clearTimeout(this.typingTimer);
        }
        this.typingTimer = setTimeout(() => this.stopTyping(), 2500);
    }

    private stopTyping(): void {
        if (this.typingTimer) {
            clearTimeout(this.typingTimer);
            this.typingTimer = null;
        }
        if (this.typingActive) {
            this.typingActive = false;
            this.typing.emit(false);
        }
    }
}
