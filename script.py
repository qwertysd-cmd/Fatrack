#!/usr/bin/env python3
from cli import main

if __name__ == "__main__":
    main()

'''
File format:
magic FENC1 (5 bytes)
salt bytes 5..20 (16 bytes)
nonce bytes 21..32 (12 bytes)
ciphertext rest
KDF:
scrypt N=32768, r=8, p=1
salt length 16
key length 32
AEAD:
AES-256-GCM with 12-byte nonce
Plaintext:
UTF-8 JSON
'''