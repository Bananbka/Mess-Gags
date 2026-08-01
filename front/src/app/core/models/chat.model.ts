export type ChatType = 'private' | 'group' | 'channel';
export type ParticipantRole = 'owner' | 'admin' | 'member';

export interface ChatParticipant {
    user_id: string;
    role: ParticipantRole;
    joined_at: string;
}

export interface Chat {
    id: string;
    chat_type: ChatType;
    title: string | null;
    avatar_url: string | null;
    unread_count: number;
    /** Opaque under E2E — the client must decrypt it to render a preview. */
    last_message: unknown;
    created_at: string;
    updated_at: string | null;
    participants: ChatParticipant[];
}

export interface UserProfile {
    id: string;
    full_name: string;
    username: string;
    email: string;
    phone_number: string;
    public_key: string;
    bio: string | null;
    avatar: string | null;
    is_active: boolean;
}

export interface UserSearchResult {
    id: string;
    full_name: string;
    username: string;
    avatar_url: string | null;
}
