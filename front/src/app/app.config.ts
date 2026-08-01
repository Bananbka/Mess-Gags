import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, inject, provideAppInitializer, provideZoneChangeDetection } from '@angular/core';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { provideRouter, withComponentInputBinding, withInMemoryScrolling } from '@angular/router';

import { routes } from './app.routes';
import { credentialsInterceptor } from './core/interceptors/credentials.interceptor';
import { ConfigService } from './core/services/config.service';
import { SessionService } from './core/services/session.service';

export const appConfig: ApplicationConfig = {
    providers: [
        provideZoneChangeDetection({ eventCoalescing: true }),
        provideRouter(routes, withComponentInputBinding(), withInMemoryScrolling({ scrollPositionRestoration: 'top' })),
        provideAnimationsAsync(),
        provideHttpClient(withInterceptors([credentialsInterceptor])),
        // provideAppInitializer rather than the deprecated APP_INITIALIZER token. Config must land
        // before the session probe, since the probe needs the resolved API base URL.
        provideAppInitializer(async () => {
            await inject(ConfigService).load();
            await inject(SessionService).restore();
        }),
    ],
};
