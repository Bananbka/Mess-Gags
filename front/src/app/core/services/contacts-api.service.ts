import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { map, Observable } from 'rxjs';

import { SuccessResponse } from '../models/api.model';
import { Contact } from '../models/chat.model';
import { ConfigService } from './config.service';

@Injectable({ providedIn: 'root' })
export class ContactsApiService {
    private readonly http = inject(HttpClient);
    private readonly configService = inject(ConfigService);

    private get apiUrl(): string {
        return this.configService.apiUrl + 'contacts/';
    }

    getContacts(): Observable<Contact[]> {
        return this.http.get<SuccessResponse<Contact[]>>(this.apiUrl).pipe(map((r) => r.data));
    }

    addContact(contactId: string, aliasName?: string): Observable<Contact> {
        return this.http
            .post<SuccessResponse<Contact>>(this.apiUrl, { contact_id: contactId, alias_name: aliasName ?? null })
            .pipe(map((r) => r.data));
    }
}
