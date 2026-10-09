"""Bounded display profiles; never part of engine/transport identity."""
import base64
import binascii
import re
import struct
import zlib


def validate_profile(value):
    if type(value) is not dict or set(value) != {'name', 'icon'}:
        raise ValueError('invalid_player_profile')
    name, icon = value['name'], value['icon']
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9 _.-]{1,24}', name) or not name.strip():
        raise ValueError('invalid_player_profile')
    name = ' '.join(name.strip().split())
    if not isinstance(icon, str) or len(icon) > 24576:
        raise ValueError('invalid_player_profile')
    if icon:
        prefix = 'data:image/png;base64,'
        if not icon.startswith(prefix):
            raise ValueError('invalid_player_profile')
        try:
            raw = base64.b64decode(icon[len(prefix):], validate=True)
            if raw[:8] != b'\x89PNG\r\n\x1a\n':
                raise ValueError('invalid PNG')
            offset, chunks, data, channels = 8, [], bytearray(), 0
            while offset < len(raw):
                if offset + 12 > len(raw):
                    raise ValueError('truncated PNG')
                length = struct.unpack_from('>I', raw, offset)[0]
                kind = raw[offset+4:offset+8]
                end = offset + 12 + length
                if end > len(raw) or binascii.crc32(raw[offset+4:end-4]) != struct.unpack_from('>I', raw, end-4)[0]:
                    raise ValueError('invalid PNG chunk')
                payload = raw[offset+8:end-4]
                if not chunks and kind != b'IHDR':
                    raise ValueError('missing PNG header')
                if kind == b'IHDR':
                    if chunks or len(payload) != 13:
                        raise ValueError('invalid PNG header')
                    w, h, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
                    if (w, h, depth, compression, filtering, interlace) != (64, 64, 8, 0, 0, 0) or color not in (2, 6):
                        raise ValueError('invalid thumbnail dimensions')
                    channels = 3 if color == 2 else 4
                elif kind == b'IDAT':
                    if b'IEND' in chunks or b'IDAT' in chunks and chunks[-1] != b'IDAT':
                        raise ValueError('invalid PNG data order')
                    data.extend(payload)
                elif kind == b'IEND':
                    if length or end != len(raw) or not data:
                        raise ValueError('invalid PNG end')
                elif kind not in (b'sRGB', b'gAMA', b'cHRM', b'pHYs'):
                    raise ValueError('unsupported thumbnail chunk')
                chunks.append(kind)
                offset = end
            if not chunks or chunks[-1] != b'IEND':
                raise ValueError('missing PNG end')
            expected = 64 * (1 + 64 * channels)
            decoder = zlib.decompressobj()
            pixels = decoder.decompress(data, expected + 1)
            if len(pixels) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or any(pixels[i] > 4 for i in range(0, expected, 1 + 64 * channels)):
                raise ValueError('invalid PNG pixels')
        except (ValueError, binascii.Error, zlib.error, struct.error):
            raise ValueError('invalid_player_profile') from None
    return {'name': name, 'icon': icon}
