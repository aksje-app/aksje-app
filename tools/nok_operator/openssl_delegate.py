#!/usr/bin/env python3
"""Delegate only CMS decryption of the pinned archive to its owner PC.
All other OpenSSL commands use the unchanged installed OpenSSL executable.
No private key is transferred. The application still verifies every archive byte.
"""
import json
import os
import socket
import sys


def main():
    args = sys.argv[1:]
    if args[:2] != ['cms','-decrypt']:
        os.execv(os.environ['NOK_SYSTEM_OPENSSL'], [os.environ['NOK_SYSTEM_OPENSSL'],*args])
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(os.environ['NOK_DECRYPT_SOCKET'])
        client.sendall(json.dumps(args).encode()+b'\n')
        response = client.makefile('rb').readline(4096)
    if json.loads(response).get('ok') is not True:
        raise ValueError('PC archive decryption failed')

if __name__ == '__main__':
    try: main()
    except Exception:
        sys.stderr.write('Private PC decryption unavailable; activation blocked\n')
        raise SystemExit(1)
