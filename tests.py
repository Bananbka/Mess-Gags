import base64
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.fernet import Fernet


def generate_e2e_keys(master_password: str):
    # 1. Генеруємо пару ключів
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Серіалізуємо у формат PEM (текст)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # 2. Шифруємо приватний ключ "Майстер-паролем"
    # (Для простоти симуляції використовуємо Fernet, який є обгорткою над AES)
    # Fernet вимагає 32-байтний ключ у base64. Робимо з пароля сурогат ключа.
    padded_password = master_password.ljust(32, 'X').encode()
    aes_key = base64.urlsafe_b64encode(padded_password)
    cipher = Fernet(aes_key)

    encrypted_private_key = cipher.encrypt(private_pem)

    return public_pem.decode(), encrypted_private_key.decode()

print(generate_e2e_keys("qweqweqwe"))