import sys
import zlib
import struct
import argparse
import ctypes
import ctypes.util

KEY = bytes([137] * 16)   # 0x89 × 16
IV  = bytes([16]  * 16)   # 0x10 × 16

def _load_twofish():
    """Carga libavutil y configura los prototipos de las funciones Twofish."""
    candidates = ['avutil', 'avutil-60', 'avutil-58', 'avutil-57', 'avutil-56',
                  'avutil-55', 'avutil-54']
    for name in candidates:
        path = ctypes.util.find_library(name)
        if not path:
            continue
        try:
            lib = ctypes.CDLL(path)
            lib.av_twofish_alloc.restype  = ctypes.c_void_p
            lib.av_twofish_alloc.argtypes = []
            lib.av_twofish_init.restype   = ctypes.c_int
            lib.av_twofish_init.argtypes  = [ctypes.c_void_p,
                                              ctypes.c_char_p,
                                              ctypes.c_int]
            lib.av_twofish_crypt.restype  = None
            lib.av_twofish_crypt.argtypes = [ctypes.c_void_p,
                                              ctypes.c_char_p,
                                              ctypes.c_char_p,
                                              ctypes.c_int,
                                              ctypes.c_char_p,
                                              ctypes.c_int]
            return lib
        except Exception:
            continue

    raise RuntimeError(
        "\nNo se encontró libavutil (FFmpeg) en el sistema.\n"
        "  Windows : descarga FFmpeg de https://ffmpeg.org/download.html\n"
        "            y agrega la carpeta bin/ al PATH del sistema.\n"
        "  Linux   : sudo apt install ffmpeg\n"
        "  macOS   : brew install ffmpeg\n"
    )


_LIB = _load_twofish()


def _twofish_ecb_encrypt(key: bytes, block: bytes) -> bytes:
    """Cifra un bloque (múltiplo de 16 bytes) con Twofish-ECB."""
    assert len(block) % 16 == 0
    ctx = _LIB.av_twofish_alloc()
    if not ctx:
        raise RuntimeError("av_twofish_alloc() devolvió NULL")
    _LIB.av_twofish_init(ctx, key, 128)
    out = ctypes.create_string_buffer(len(block))
    _LIB.av_twofish_crypt(ctx, out, block, len(block) // 16, None, 0)
    return out.raw


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def _cmac(key: bytes, data: bytes) -> bytes:
    """OMAC1/CMAC usando Twofish como cifrador de bloque."""
    BLOCK = 16

    def enc(b): return _twofish_ecb_encrypt(key, b)

    # Generar subclaves K1, K2
    L  = enc(bytes(BLOCK))
    K1 = int.to_bytes((int.from_bytes(L, 'big') << 1) & ((1 << 128) - 1), 16, 'big')
    if L[0] >> 7:
        K1 = bytes(K1[i] ^ (0x87 if i == 15 else 0) for i in range(BLOCK))
    K2 = int.to_bytes((int.from_bytes(K1, 'big') << 1) & ((1 << 128) - 1), 16, 'big')
    if K1[0] >> 7:
        K2 = bytes(K2[i] ^ (0x87 if i == 15 else 0) for i in range(BLOCK))

    if not data:
        return enc(_xor(b'\x80' + b'\x00' * 15, K2))

    n        = (len(data) + BLOCK - 1) // BLOCK
    complete = len(data) % BLOCK == 0
    X        = bytes(BLOCK)

    for i in range(n - 1):
        X = enc(_xor(X, data[i * BLOCK:(i + 1) * BLOCK]))

    last = data[(n - 1) * BLOCK:]
    if complete:
        last_block = _xor(last, K1)
    else:
        pad        = last + b'\x80' + b'\x00' * (BLOCK - len(last) - 1)
        last_block = _xor(pad, K2)

    return enc(_xor(X, last_block))


def _ctr(key: bytes, nonce_block: bytes, data: bytes) -> bytes:
    """Modo CTR usando Twofish."""
    BLOCK   = 16
    result  = bytearray()
    counter = int.from_bytes(nonce_block, 'big')
    for i in range(0, len(data), BLOCK):
        ks = _twofish_ecb_encrypt(key, counter.to_bytes(BLOCK, 'big'))
        counter = (counter + 1) & ((1 << 128) - 1)
        result.extend(_xor(ks, data[i:i + BLOCK]))
    return bytes(result)

def _twofish_eax_encrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    """
    Cifra `data` con Twofish en modo EAX.
    Retorna ciphertext + tag de autenticación (16 bytes al final).
    Equivalente exacto a Crypto++ EAX<Twofish> con los mismos key e iv.
    """
    BLOCK      = 16
    N          = _cmac(key, bytes(BLOCK - 1) + b'\x00' + iv)   # OMAC_0(nonce)
    ciphertext = _ctr(key, N, data)                              # CTR encrypt
    C          = _cmac(key, bytes(BLOCK - 1) + b'\x02' + ciphertext)
    H          = _cmac(key, bytes(BLOCK - 1) + b'\x01')         # sin header
    tag        = _xor(_xor(N, H), C)[:BLOCK]
    return ciphertext + tag

def _compress_with_header(data: bytes) -> bytes:
    """Etapa 1: zlib + cabecera de 4 bytes con el tamaño original."""
    return len(data).to_bytes(4, 'big') + zlib.compress(data)


def _xor_stage(data: bytes) -> bytes:
    """Etapa 2: data[i] ^= (len - i) & 0xFF"""
    n = len(data)
    return bytes(b ^ ((n - i) & 0xFF) for i, b in enumerate(data))


def _final_obfuscation(data: bytes) -> bytes:
    """Etapa 4: output[len-1-i] = data[i] ^ ((len - i*len) & 0xFF)"""
    n   = len(data)
    out = bytearray(n)
    for i, b in enumerate(data):
        out[n - 1 - i] = b ^ ((n - i * n) & 0xFF)
    return bytes(out)

def encriptar(ruta_origen: str, ruta_salida: str) -> bool:
    """
    Convierte un archivo XML al formato binario PKT/PKA de Packet Tracer.

    Args:
        ruta_origen: ruta al archivo .xml de entrada
        ruta_salida: ruta al archivo .pkt / .pka de salida
    """
    with open(ruta_origen, 'rb') as f:
        xml = f.read()

    etapa1 = _compress_with_header(xml)       # compress + header
    etapa2 = _xor_stage(etapa1)               # obfuscation pre-cifrado
    etapa3 = _twofish_eax_encrypt(etapa2, KEY, IV)  # Twofish-EAX
    pkt    = _final_obfuscation(etapa3)        # obfuscation post-cifrado

    with open(ruta_salida, 'wb') as f:
        f.write(pkt)
    return True

def main():
    parser = argparse.ArgumentParser(
        description='Convierte XML → PKT/PKA (Cisco Packet Tracer)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python xml_to_pkt.py mi_red.xml       mi_red.pkt
  python xml_to_pkt.py actividad.xml    actividad.pka
        """
    )
    parser.add_argument('input',  help='Archivo XML de entrada')
    parser.add_argument('output', help='Archivo PKT/PKA de salida')
    args = parser.parse_args()

    try:
        print(f"[*] Leyendo  : {args.input}")
        encriptar(args.input, args.output)
        print(f"[+] Generado : {args.output}")
    except FileNotFoundError:
        print(f"Error: no se encontró '{args.input}'", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()