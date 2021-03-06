##############################################################################
#
# This file is part of JA2 Open Toolset
#
# JA2 Open Toolset is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# JA2 Open Toolset is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with JA2 Open Toolset.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import os
import io
import struct
from collections import Iterable
from PIL import Image, ImageFile, ImagePalette

from .common import Ja2FileHeader
from ..content import Image16Bit, Images8Bit, SubImage8Bit
from .ETRLE import etrle_decompress, etrle_compress


class Sti16BitHeader(Ja2FileHeader):
    fields = [
        ('red_color_mask', 'L'),
        ('green_color_mask', 'L'),
        ('blue_color_mask', 'L'),
        ('alpha_channel_mask', 'L'),
        ('red_color_depth', 'B'),
        ('green_color_depth', 'B'),
        ('blue_color_depth', 'B'),
        ('alpha_channel_depth', 'B')
    ]


class Sti8BitHeader(Ja2FileHeader):
    fields = [
        ('number_of_palette_colors', 'L'),
        ('number_of_images', 'H'),
        ('red_color_depth', 'B'),
        ('green_color_depth', 'B'),
        ('blue_color_depth', 'B'),
        (None, '11x')
    ]


class StiHeader(Ja2FileHeader):
    fields = [
        ('file_identifier', '4s'),
        ('initial_size', 'L'),
        ('size_after_compression', 'L'),
        ('transparent_color', 'L'),
        ('flags', 'L'),
        ('height', 'H'),
        ('width', 'H'),
        ('format_specific_header', '20s'),
        ('color_depth', 'B'),
        (None, '3x'),
        ('aux_data_size', 'L'),
        (None, '12x')
    ]

    flags = {
        'flags': {
            'AUX_OBJECT_DATA': 0,
            'RGB': 2,
            'INDEXED': 3,
            'ZLIB': 4,
            'ETRLE': 5
        }
    }


class StiSubImageHeader(Ja2FileHeader):
    fields = [
        ('offset', 'L'),
        ('length', 'L'),
        ('offset_x', 'H'),
        ('offset_y', 'H'),
        ('height', 'H'),
        ('width', 'H')
    ]


class AuxObjectData(Ja2FileHeader):
    fields = [
        ('wall_orientation', 'B'),
        ('number_of_tiles', 'B'),
        ('tile_location_index', 'H'),
        (None, '3x'),
        ('current_frame', 'B'),
        ('number_of_frames', 'B'),
        ('flags', 'B'),
        (None, '6x')
    ]

    flags = {
        'flags': {
            'FULL_TILE': 0,
            'ANIMATED_TILE': 1,
            'DYNAMIC_TILE': 2,
            'INTERACTIVE_TILE': 3,
            'IGNORES_HEIGHT': 4,
            'USES_LAND_Z': 5,
        }
    }


def _get_filelike(file):
    if isinstance(file, str):
        filename = os.path.expanduser(os.path.expandvars(file))
        filename = os.path.normpath(os.path.abspath(filename))
        return open(filename, 'rb')
    else:
        return file


def is_16bit_sti(file):
    f = _get_filelike(file)
    header = StiHeader.from_bytes(f.read(StiHeader.get_size()))
    f.seek(0, 0)
    if header['file_identifier'] != b'STCI':
        return False
    return header.get_flag('flags', 'RGB') and not header.get_flag('flags', 'INDEXED')


def is_8bit_sti(file):
    f = _get_filelike(file)
    header = StiHeader.from_bytes(f.read(StiHeader.get_size()))
    f.seek(0, 0)
    if header['file_identifier'] != b'STCI':
        return False
    return header.get_flag('flags', 'INDEXED') and not header.get_flag('flags', 'RGB')


def load_16bit_sti(file):
    if not is_16bit_sti(file):
        raise ValueError('Not a 16bit sti file')
    f = _get_filelike(file)

    header = StiHeader.from_bytes(f.read(StiHeader.get_size()))
    header_16bit = Sti16BitHeader.from_bytes(header['format_specific_header'])

    number_of_pixels = header['width'] * header['height']
    red_color_mask = header_16bit['red_color_mask']
    green_color_mask = header_16bit['green_color_mask']
    blue_color_mask = header_16bit['blue_color_mask']
    pixel_bytes = struct.unpack('<{}H'.format(number_of_pixels), f.read(number_of_pixels * 2))

    rgb_image_buffer = io.BytesIO()
    for pixel_short in pixel_bytes:
        r = (pixel_short & red_color_mask) >> 8
        g = (pixel_short & green_color_mask) >> 3
        b = (pixel_short & blue_color_mask) << 3
        rgb_image_buffer.write(struct.pack('BBB', r, g, b))
    rgb_image_buffer.seek(0, os.SEEK_SET)

    img = Image.frombytes(
        'RGB',
        (header['width'], header['height']),
        rgb_image_buffer.read(),
        'raw'
    )

    return Image16Bit(img)


def _load_raw_sub_image(f, palette, sub_image_header):
    compressed_data = f.read(sub_image_header['length'])
    uncompressed_data = etrle_decompress(compressed_data)

    img = Image.frombytes(
        'P',
        (sub_image_header['width'], sub_image_header['height']),
        uncompressed_data,
        'raw'
    )
    img.putpalette(palette)

    return img


def _to_sub_image(image, sub_image_header, aux_image_data):
    aux_data = {
        'wall_orientation': aux_image_data['wall_orientation'],
        'number_of_tiles': aux_image_data['number_of_tiles'],
        'tile_location_index': aux_image_data['tile_location_index'],
        'current_frame': aux_image_data['current_frame'],
        'number_of_frames': aux_image_data['number_of_frames'],
        'full_tile': aux_image_data.get_flag('flags', 'FULL_TILE'),
        'animated_tile': aux_image_data.get_flag('flags', 'ANIMATED_TILE'),
        'dynamic_tile': aux_image_data.get_flag('flags', 'DYNAMIC_TILE'),
        'interactive_tile': aux_image_data.get_flag('flags', 'INTERACTIVE_TILE'),
        'ignores_height': aux_image_data.get_flag('flags', 'IGNORES_HEIGHT'),
        'uses_land_z': aux_image_data.get_flag('flags', 'USES_LAND_Z'),
    } if aux_image_data else None

    return SubImage8Bit(
        image,
        offsets=(sub_image_header['offset_x'], sub_image_header['offset_y']),
        aux_data=aux_data
    )


def load_8bit_sti(file):
    if not is_8bit_sti(file):
        raise ValueError('Not a non-animated 8bit sti file')
    f = _get_filelike(file)

    header = StiHeader.from_bytes(f.read(StiHeader.get_size()))
    header_8bit = Sti8BitHeader.from_bytes(header['format_specific_header'])

    palette_colors = [struct.unpack('BBB', f.read(3)) for _ in range(header_8bit['number_of_palette_colors'])]
    colors_in_right_order = [x[0] for x in palette_colors] + [x[1] for x in palette_colors] + [x[2] for x in palette_colors]
    palette = ImagePalette.ImagePalette("RGB", colors_in_right_order, 3 * header_8bit['number_of_palette_colors'])

    sub_image_headers = [StiSubImageHeader.from_bytes(f.read(StiSubImageHeader.get_size()))
                         for _ in range(header_8bit['number_of_images'])]

    images = [_load_raw_sub_image(f, palette, s) for s in sub_image_headers]

    aux_image_data = [None] * len(images)
    if header['aux_data_size'] != 0:
        aux_image_data = [AuxObjectData.from_bytes(f.read(AuxObjectData.get_size()))
                          for _ in range(header_8bit['number_of_images'])]

    return Images8Bit(
        list([_to_sub_image(i, s, a) for i, s, a in zip(images, sub_image_headers, aux_image_data)]),
        palette,
        width=header['width'],
        height=header['height']
    )


def save_16bit_sti(ja2_image, file):
    if not isinstance(ja2_image, Image16Bit):
        raise ValueError('Input needs to be of type Image16Bit')

    width, height = ja2_image.size[0], ja2_image.size[1]
    image_size = width * height * 2
    raw_image = ja2_image.image
    format_specific_header = Sti16BitHeader(
        red_color_mask=0xF800,
        green_color_mask=0x7E0,
        blue_color_mask=0x1F,
        alpha_channel_mask=0,
        red_color_depth=5,
        green_color_depth=6,
        blue_color_depth=5,
        alpha_channel_depth=0
    )
    header = StiHeader(
        file_identifier=b'STCI',
        initial_size=image_size,
        size_after_compression=image_size,
        transparent_color=0,
        width=width,
        height=height,
        format_specific_header=bytes(format_specific_header),
        color_depth=16,
        aux_data_size=0,
        flags=0
    )
    header.set_flag('flags', 'RGB', True)

    file.write(bytes(header))

    for y in range(height):
        for x in range(width):
            pix = raw_image.getpixel((x, y))
            r = pix[0] >> 3
            g = pix[1] >> 3
            b = pix[2] >> 3
            rgb = b + (g << 6) + (r << 11)
            file.write(struct.pack('<H', rgb))


def _sub_image_to_bytes(sub_image):
    width = sub_image.image.size[0]
    height = sub_image.image.size[1]
    compressed_buffer = io.BytesIO()
    uncompressed_data = sub_image.image.tobytes()

    for i in range(height):
        compressed_buffer.write(etrle_compress(uncompressed_data[i*width:(i+1)*width]))
        compressed_buffer.write(b'\x00')
    return compressed_buffer.getvalue()


def _palette_to_bytes(palette):
    buffer = io.BytesIO()

    if not palette.rawmode:
        wrong_order = palette.tobytes()
        number_of_colors = int(len(wrong_order) / 3)
        for i in range(number_of_colors):
            buffer.write(wrong_order[i:i+1] + wrong_order[number_of_colors+i:number_of_colors+i+1] + wrong_order[2*number_of_colors+i:2*number_of_colors+i+1])
    else:
        buffer.write(palette.palette)

    return buffer.getvalue()


def save_8bit_sti(ja2_images, file):
    if not isinstance(ja2_images, Images8Bit):
        raise ValueError('Input needs to be of type Images8Bit')

    aux_data = list(i.aux_data for i in ja2_images.images if i.aux_data is not None)
    if len(aux_data) != 0 and not len(aux_data) == len(ja2_images):
        raise ValueError('Either all or none of the sub_images needs to have aux_data to save')

    palette_bytes = _palette_to_bytes(ja2_images.palette).ljust(256 * 3, b'\x00')

    initial_size = ja2_images.width * ja2_images.height
    compressed_images = list(_sub_image_to_bytes(s) for s in ja2_images.images)
    compressed_image_sizes = list(len(i) for i in compressed_images)
    offsets = list(sum(compressed_image_sizes[:i]) for i in range(len(compressed_images)))
    size_after_compression = sum(compressed_image_sizes)
    sub_image_headers = list(
        StiSubImageHeader(
            offset=offset,
            length=comp_size,
            offset_x=sub.offsets[0],
            offset_y=sub.offsets[1],
            height=sub.image.size[1],
            width=sub.image.size[0]
        )
        for sub, comp_size, offset in zip(ja2_images.images, compressed_image_sizes, offsets)
    )

    format_specific_header = Sti8BitHeader(
        number_of_palette_colors=256,
        number_of_images=len(ja2_images),
        red_color_depth=8,
        green_color_depth=8,
        blue_color_depth=8
    )
    header = StiHeader(
        file_identifier=b'STCI',
        initial_size=initial_size,
        size_after_compression=size_after_compression,
        transparent_color=0,
        width=ja2_images.width,
        height=ja2_images.height,
        format_specific_header=bytes(format_specific_header),
        color_depth=8,
        aux_data_size=len(aux_data) * AuxObjectData.get_size(),
        flags=0
    )
    header.set_flag('flags', 'INDEXED', True)
    header.set_flag('flags', 'ETRLE', True)

    file.write(bytes(header))
    file.write(palette_bytes)
    for sub_image_header in sub_image_headers:
        file.write(bytes(sub_image_header))
    for compressed in compressed_images:
        file.write(compressed)
    for aux in aux_data:
        aux_header = AuxObjectData(
            wall_orientation=aux['wall_orientation'],
            number_of_tiles=aux['number_of_tiles'],
            tile_location_index=aux['tile_location_index'],
            current_frame=aux['current_frame'],
            number_of_frames=aux['number_of_frames'],
            flags=0
        )
        aux_header.set_flag('flags', 'FULL_TILE', aux['full_tile'])
        aux_header.set_flag('flags', 'ANIMATED_TILE', aux['animated_tile'])
        aux_header.set_flag('flags', 'DYNAMIC_TILE', aux['dynamic_tile'])
        aux_header.set_flag('flags', 'INTERACTIVE_TILE', aux['interactive_tile'])
        aux_header.set_flag('flags', 'IGNORES_HEIGHT', aux['ignores_height'])
        aux_header.set_flag('flags', 'USES_LAND_Z', aux['uses_land_z'])
        file.write(bytes(aux_header))


def _color_components(color, spec):
    """Convert a raw color value matching the spec to byte color components."""
    def component(color, mask, bits):
        value = color & mask
        if value == mask:
            return 255 # always pure white/opaque
        if bits > 8: # discard extra bits
            shift = mask.bit_length() - 8
            return value >> shift
        # mimic SDL_GetRGBA (produces the entire 8-bit [0..255] range)
        shift = mask.bit_length() - bits
        max_value = (1 << bits) - 1
        return ((value >> shift) * 255) // max_value
    components = [component(color, mask, bits) for mask, bits in zip(spec[:4], spec[4:8])]
    return tuple(components)


def _color_bytes(components, spec):
    """Convert color components to a byte array matching the spec."""
    masks = spec[:4]
    bits = spec[4:8]
    depth = spec[8]
    assert isinstance(depth, int) and depth >= sum(bits) and depth % 8== 0
    color = 0
    for byte, mask in zip(components, masks):
        assert isinstance(byte, int) and byte >= 0 and byte <= 255
        assert isinstance(mask, int) and mask >= 0 and mask <= 0xffffffff
        if byte == 0 or mask == 0:
            continue # already 0
        shift = mask.bit_length() - 8
        if shift > 0:
            color |= (byte << shift) & mask
        elif shift < 0:
            color |= (byte >> -shift) & mask
        else:
            color |= byte & mask
    if depth == 8:
        return struct.pack('<B', color)
    elif depth == 16:
        return struct.pack('<H', color)
    elif depth == 24:
        return struct.pack('<HB', color & 0xffff, color >> 16)
    else:
        assert depth >= 32
        extra = [0 for _ in range((depth - 32) // 8)] # 0 in extra bytes
        return struct.pack('<L' + 'B' * len(extra), color, *extra)


def validate_spec(spec):
    """Validates a spec with asserts."""
    assert isinstance(spec, Iterable), "spec type %r" % spec
    assert len(spec) == 9, "spec len %r" % spec
    masks = spec[:4]
    depths = spec[4:8]
    color_depth = spec[8]
    for mask, depth in zip(masks, depths):
        assert isinstance(mask, int), "mask type %r" % mask
        assert isinstance(depth, int), "depth type %r" % depth
        assert mask >= 0 and mask <= 0xffffffff, "mask value %r" % mask
        assert depth >= 0 and depth <= 32, "depth value %r" % depth
        assert mask & ~(((2 ** depth) - 1) << (mask.bit_length() - depth)) == 0, "mask bits %r %r" % (mask, depth)
    assert isinstance(color_depth, int), "color depth type %r" % color_depth
    assert color_depth >= 0 and color_depth <= 0xff and color_depth % 8 == 0, "color depth value %r" % color_depth
    assert sum(depths) <= color_depth, "color depth size %r %r" % (depths, color_depth)


def validate_flags(flags):
    """Validates flags with asserts."""
    assert isinstance(flags, Iterable), "flags type %r" % flags
    assert ('RGB' in flags) != ('INDEXED' in flags), "either RGB or INDEXED %r" % flags
    for flag in flags:
        assert isinstance(flag, str), "flag type %r" % flag
        assert flag in StiHeader.flags['flags'], "flag value %r" % flag
    assert len(set(flags)) == len(flags), "duplicate flags %r" % flags


class StiImagePlugin(ImageFile.ImageFile):
    """
    Image plugin for Pillow that can load STI files.

    Images can be RGB or INDEXED.
    INDEXED images can be encoded with ETRLE.

    The meaning of ETRLE is unknown.
    It is a run-length encoding applied to the indexes of each line of an image.
    It uses control bytes, which contain a length in the 7 lower bits.
    Each line ends with a control byte that has length 0.
    Sequences of up to 127 indexes equal to 0 are compressed into 1 control byte that has the high bit set to 1.
    Other sequences of up to 127 indexes are prefixed with 1 control byte that has the high bit set to 0.
    """

    format = 'STCI'
    format_description = "Sir-Tech's Crazy Image"

    def _open(self):
        """Reads file information without image data."""
        self.fp.seek(0, 0) # from start
        header = StiHeader.from_bytes(self.fp.read(StiHeader.get_size()))
        if header['file_identifier'] != b'STCI':
            raise SyntaxError('not a STCI file')
        assert not header.get_flag('flags', 'ZLIB'), "TODO ZLIB compression" # XXX need example
        self.size = (header['width'], header['height'])
        if header.get_flag('flags', 'RGB'):
            # raw color image
            assert not header.get_flag('flags', 'INDEXED'), "RGB and INDEXED at the same time"
            assert not header.get_flag('flags', 'AUX_OBJECT_DATA'), "TODO aux object data in RGB" # XXX need example
            rgb_header = Sti16BitHeader.from_bytes(header['format_specific_header'])
            spec = (
                rgb_header['red_color_mask'], rgb_header['green_color_mask'], rgb_header['blue_color_mask'], rgb_header['alpha_channel_mask'],
                rgb_header['red_color_depth'], rgb_header['green_color_depth'], rgb_header['blue_color_depth'], rgb_header['alpha_channel_depth'],
                header['color_depth']
            )
            if rgb_header['alpha_channel_mask'] == 0:
                self.mode = 'RGB'
            else:
                self.mode = 'RGBA'
            self.tile = [ # single image
                (self.format, (0, 0) + self.size, StiHeader.get_size(), ('rgb', spec, header['size_after_compression']))
            ]
            self.info['header'] = header
            self.info['rgb_header'] = rgb_header
            self.info['boxes'] = [(0, 0) + self.size]
        elif header.get_flag('flags', 'INDEXED'):
            # palette color image
            indexed_header = Sti8BitHeader.from_bytes(header['format_specific_header'])
            assert indexed_header['number_of_palette_colors'] == 256
            assert indexed_header['red_color_depth'] == 8
            assert indexed_header['green_color_depth'] == 8
            assert indexed_header['blue_color_depth'] == 8
            num_bytes = indexed_header['number_of_palette_colors'] * 3
            raw = struct.unpack('<{}B'.format(num_bytes), self.fp.read(num_bytes))
            self.mode = 'P'
            self.palette = ImagePalette.ImagePalette("RGB", raw[0::3] + raw[1::3] + raw[2::3])
            self.palette.dirty = True
            if header.get_flag('flags', 'ETRLE'): # etrle encoded indexes, multiple subimages
                # TODO open subimages as frames instead of composing an image?
                num_images = indexed_header['number_of_images']
                assert num_images > 0, "TODO 0 etrle subimages" # XXX need example
                subimage_headers = [StiSubImageHeader.from_bytes(self.fp.read(StiSubImageHeader.get_size())) for _ in range(num_images)]
                boxes = self._generate_boxes(subimage_headers)
                offset = self.fp.tell()
                self.tile = [
                    (self.format, (0, 0) + self.size, offset, ('fill', [header['transparent_color']])) # XXX wall index is another possibility
                ]
                for box, subimage in zip(boxes, subimage_headers):
                    parameters = ('etrle', header['transparent_color'], subimage['length'])
                    tile = (self.format, box, offset + subimage['offset'], parameters)
                    self.tile.append(tile)
                self.info['boxes'] = boxes
                self.info['subimage_headers'] = subimage_headers
                if header.get_flag('flags', 'AUX_OBJECT_DATA'):
                    self.fp.seek(header['size_after_compression'], 1) # from current
                    aux_object_data = [AuxObjectData.from_bytes(self.fp.read(AuxObjectData.get_size())) for _ in range(num_images)]
                    self.info['aux_object_data'] = aux_object_data
            else: # raw indexes
                assert not header.get_flag('flags', 'AUX_OBJECT_DATA'), "TODO INDEXED and AUX_OBJECT_DATA without ETRLE" # XXX need example
                self.tile = [
                    (self.format, (0, 0) + self.size, self.fp.tell(), ('indexes', header['width'] * header['height']))
                ]
            self.info['header'] = header
            self.info['indexed_header'] = indexed_header
            self.info["transparency"] = header['transparent_color']
        else:
            raise SyntaxError('unknown image mode')

    def _generate_boxes(self, subimage_headers):
        """
        The main image size of indexed images seems to be the canvas size.
        STIconvert.cc has code to generate subimages by processing wall indexes (WI=255)
        At least one official STI image can't fit all subimages in the canvas, so this function resizes the image.
        """
        assert len(subimage_headers) > 0, "TODO 0 subimages" # XXX need example
        boxes = []
        width = 0
        height = 0
        for subimage in subimage_headers:
            if width > 0:
                width += 1 # 1 pixel vertical line between images
            box = (width, 0, width + subimage['width'], subimage['height'])
            boxes.append(box)
            width += subimage['width']
            if height < subimage['height']:
                height = subimage['height']
        self.size = width, height
        return boxes

    @staticmethod
    def _save_colors_image(img, fd):
        """
        Data in dictionary `img.encoderinfo`:

         * flags - (list) list of flags, requires flag 'RGB'
         * spec  - (spec) optional rawmode string or spec, default is determined by StiImageEncoder, examples in RAWMODE_SPEC
        """
        flags = img.encoderinfo['flags']
        validate_flags(flags)
        assert 'RGB' in flags
        assert 'INDEXED' not in flags
        assert 'ETRLE' not in flags
        assert 'ZLIB' not in flags # XXX needs example
        assert 'AUX_OBJECT_DATA' not in flags # XXX needs example
        encoder = StiImageEncoder('RGB', 'colors', img.encoderinfo.get('spec'))
        spec = encoder.spec
        validate_spec(spec)
        encoder.setimage(img.im)
        encoder.setfd(fd)
        fd.seek(StiHeader.get_size(), 0) # from start
        num_bytes, errcode = encoder.encode_to_pyfd()
        if errcode < 0:
            raise IOError("encoder error %d when writing RGB sti image file" % errcode)
        fd.truncate()
        rgb_header = Sti16BitHeader(
            red_color_mask = spec[0],
            green_color_mask = spec[1],
            blue_color_mask = spec[2],
            alpha_channel_mask = spec[3],
            red_color_depth = spec[4],
            green_color_depth = spec[5],
            blue_color_depth = spec[6],
            alpha_channel_depth = spec[7]
        )
        width, height = img.size
        color_depth = spec[8]
        header = StiHeader(
            file_identifier = b'STCI',
            initial_size = num_bytes,
            size_after_compression = num_bytes,
            transparent_color = 0,
            width = width,
            height = height,
            format_specific_header = bytes(rgb_header),
            color_depth = color_depth,
            aux_data_size = 0,
            flags = 0
        )
        for flag in flags:
            header.set_flag('flags', flag, True)
        fd.seek(0, 0) # from start
        fd.write(bytes(header))

    @staticmethod
    def _save_indexes_image(img, fd):
        """
        Data in dictionary `img.encoderinfo`:

         * flags - (list) list of flags
         * transparent - (list) optional transparent palette index, default: 0
        """
        flags = img.encoderinfo['flags']
        validate_flags(flags)
        assert 'INDEXED' in flags
        assert 'ETRLE' not in flags
        assert 'RGB' not in flags
        assert 'ZLIB' not in flags # XXX needs example
        assert 'AUX_OBJECT_DATA' not in flags # XXX needs example
        transparent = img.encoderinfo.get('transparent', 0) # XXX maybe ETRLE only?
        assert isinstance(transparent, int), "transparent %r" % transparent
        assert img.mode in ['P']
        assert img.palette is not None
        # write image data
        fd.seek(StiHeader.get_size(), 0) # from start
        data = img.palette.tobytes() # rgb bands
        assert len(data) == 256 * 3
        data = [x for i in range(256) for x in data[i::256]] # rgb colors
        fd.write(bytes(data))
        encoder = StiImageEncoder('P', 'indexes')
        encoder.setimage(img.im)
        encoder.setfd(fd)
        num_bytes, errcode = encoder.encode_to_pyfd()
        if errcode < 0:
            raise IOError("encoder error %d when writing INDEXED sti image file" % errcode)
        fd.truncate()
        # write header
        indexed_header = Sti8BitHeader(
            number_of_palette_colors = 256,
            number_of_images = 0, # XXX assuming ETRLE only
            red_color_depth = 8,
            green_color_depth = 8,
            blue_color_depth = 8
        )
        width, height = img.size
        header = StiHeader(
            file_identifier = b'STCI',
            initial_size = num_bytes,
            size_after_compression = num_bytes,
            transparent_color = transparent,
            width = width,
            height = height,
            format_specific_header = bytes(indexed_header),
            color_depth = 8,
            aux_data_size = 0,
            flags = 0
        )
        for flag in flags:
            header.set_flag('flags', flag, True)
        fd.seek(0, 0) # from start
        fd.write(bytes(header))

    @staticmethod
    def _save_etrle_images(img, fd):
        """
        Data in dictionary `img.encoderinfo`:

         * flags - (list) list of flags, 'INDEXED' is required
         * append_images - (list) optional list of extra images, default: []
         * transparent - (list) optional transparent RGB color , default: None
         * semi_transparent - (str) optional string indicating how to handle semi transparent pixels, default: None
           * 'transparent': make them transparent
           * 'opaque': make them opaque
         * offsets - (list) list of (x,y) offsets for each image, default: [], missing offsets default to (0,0)
         * aux_object_data - (list) optional list of AuxObjectData, default: [], missing data defaults to AuxObjectData(), re   uires flag 'AUX_OBJECT_DATA'
        """
        flags = img.encoderinfo['flags']
        validate_flags(flags)
        assert 'INDEXED' in flags
        assert 'ETRLE' in flags
        assert 'RGB' not in flags
        assert 'ZLIB' not in flags # XXX needs example
        images = [img] + img.encoderinfo.get('append_images', [])
        num_images = len(images)
        transparent = img.encoderinfo.get('transparent')
        assert transparent is None or len(transparent) == 3, "transparent %r" % transparent
        semi_transparent = img.encoderinfo.get('semi_transparent')
        assert semi_transparent in [None, 'transparent', 'opaque'], "semi_transparent %r" % semi_transparent
        offsets = img.encoderinfo.get('offsets', [])
        assert isinstance(offsets, Iterable), "offsets %r" % offsets
        if num_images > len(offsets):
            offsets += [None] * (num_images - len(offsets))
        aux_object_data = img.encoderinfo.get('aux_object_data', [])
        assert isinstance(aux_object_data, Iterable), "aux_object_data %r" % aux_object_data
        if num_images > len(aux_object_data):
            aux_object_data += [None] * (num_images - len(aux_object_data))
        # convert images to a shared palette
        palette = ImagePalette.ImagePalette()
        index = palette.getcolor(transparent or (0, 0, 0))
        assert index == 0 # XXX assuming index 0 is transparent
        indexed = []
        for img in images:
            data = bytearray()
            img = img.convert('RGBA')
            for color in img.getdata():
                rgb = color[:3]
                a = color[3]
                if a != 0 and a != 255:
                    if semi_transparent == 'transparent':
                        a = 0
                    elif semi_transparent == 'opaque':
                        a = 255
                    else:
                        raise ValueError("semi transparent color found, set `semi_transparent` to 'transparent' or 'opaque' {}".format(color))
                if a == 0:
                    data.append(0) # transparent
                else:
                    data.append(palette.getcolor(rgb))
            indexed.append(bytes(data))
        # write image data
        fd.seek(StiHeader.get_size(), 0) # from start
        palette_bands = palette.tobytes()
        assert len(palette_bands) == 256 * 3
        palette_colors = bytes([x for i in range(256) for x in palette_bands[i::256]])
        fd.write(palette_colors)
        compressed = []
        offset = 0
        for i in range(num_images):
            img = Image.new('P', images[i].size)
            img.putpalette(palette)
            img.putdata(indexed[i])
            data = img.tobytes(StiImagePlugin.format, 'etrle') # uses StiImageEncoder
            offset_x, offset_y = offsets[i] or (0, 0) # default offset
            width, height = images[i].size
            subimage_header = StiSubImageHeader(
                offset = offset,
                length = len(data),
                offset_x = offset_x,
                offset_y = offset_y,
                height = height,
                width = width
            )
            fd.write(bytes(subimage_header))
            compressed.append(data)
            offset += len(data)
        for data in compressed:
            fd.write(data)
        aux_data_size = 0
        if 'AUX_OBJECT_DATA' in flags:
            data = b"".join([bytes(x or AuxObjectData()) for x in aux_object_data[:num_images]])
            aux_data_size = len(data)
            fd.write(data)
        fd.truncate()
        indexed_header = Sti8BitHeader(
            number_of_palette_colors = 256,
            number_of_images = num_images,
            red_color_depth = 8,
            green_color_depth = 8,
            blue_color_depth = 8
        )
        width, height = img.size
        header = StiHeader(
            file_identifier = b'STCI',
            initial_size = sum([len(x) for x in indexed]),
            size_after_compression = offset,
            transparent_color = 0, # XXX assuming palette index 0 is transparent
            width = width,
            height = height,
            format_specific_header = bytes(indexed_header),
            color_depth = 8,
            aux_data_size = aux_data_size,
            flags = 0
        )
        for flag in flags:
            header.set_flag('flags', flag, True)
        # write to file
        fd.seek(0, 0) # from start
        fd.write(bytes(header))

    @staticmethod
    def _save_handler(img, fd, filename):
        """
        Handler for `Image.save` without `save_all=True`.

        Data in dictionary `img.encoderinfo`:

         * flags - (list) list of flags, default: ['RGB']
         * ... - see _save_colors_image, _save_indexes_image, _save_etrle_images
        """
        flags = img.encoderinfo.get('flags', ['RGB'])
        validate_flags(flags)
        img.encoderinfo['flags'] = flags
        if 'RGB' in flags:
            return StiImagePlugin._save_colors_image(img, fd)
        if 'INDEXED' in flags:
            if 'ETRLE' in flags:
                return StiImagePlugin._save_etrle_images(img, fd)
            return StiImagePlugin._save_indexes_image(img, fd)
        raise NotImplementedError("%r" % img.encoderinfo)

    @staticmethod
    def _save_all_handler(img, fd, filename):
        """
        Handler for `Image.save` with `save_all=True`.

        Data in dictionary `img.encoderinfo`:

         * flags - (list) list of flags, default: ['INDEXED', 'ETRLE']
         * append_images - (list) optional list of extra images, default: []
         * ... - see _save_colors_image, _save_indexes_image, _save_etrle_images
        """
        flags = img.encoderinfo.get('flags', ['INDEXED', 'ETRLE'])
        append_images = img.encoderinfo.get('append_images', [])
        validate_flags(flags)
        assert isinstance(append_images, Iterable), "append_images %r" % append_images
        img.encoderinfo['flags'] = flags
        img.encoderinfo['append_images'] = append_images
        num_images = 1 + len(append_images)
        if len(append_images) > 0:
            return StiImagePlugin._save_etrle_images(img, fd)
        else:
            return StiImagePlugin._save_handler(img, fd, filename)


"""Reference map of rawmodes to specs. They may or may not be supported by raw_encoder/raw_decoder."""
RAWMODE_SPEC = {
    'BGR;16': (0xf800,0x07e0,0x001f,0x0000, 5,6,5,0, 16),
    'BGR;15': (0x7c00,0x03e0,0x001f,0x0000, 5,5,5,0, 16),
    'BGRA;15': (0x7c00,0x03e0,0x001f,0x8000, 5,5,5,1, 16),
    'RGBA;15': (0x001f,0x03e0,0x7c00,0x8000, 5,5,5,1, 16),
    'RGB;4B': (0x000f,0x00f0,0x0f00,0x0000, 4,4,4,0, 16),
    'RGBA;4B': (0x000f,0x00f0,0x0f00,0xf000, 4,4,4,4, 16),

    'BGR': (0xff0000,0x00ff00,0x0000ff,0x000000, 8,8,8,0, 24),
    'RGB': (0x0000ff,0x00ff00,0xff0000,0x000000, 8,8,8,0, 24),

    'ABGR': (0xff000000,0x00ff0000,0x0000ff00,0x000000ff, 8,8,8,8, 32),
    'XBGR': (0xff000000,0x00ff0000,0x0000ff00,0x00000000, 8,8,8,0, 32),
    'ARGB': (0x0000ff00,0x00ff0000,0xff000000,0x000000ff, 8,8,8,8, 32),
    'XRGB': (0x0000ff00,0x00ff0000,0xff000000,0x00000000, 8,8,8,0, 32),
    'BGRA': (0x00ff0000,0x0000ff00,0x000000ff,0xff000000, 8,8,8,8, 32),
    'BGRX': (0x00ff0000,0x0000ff00,0x000000ff,0x00000000, 8,8,8,0, 32),
    'RGBA': (0x000000ff,0x0000ff00,0x00ff0000,0xff000000, 8,8,8,8, 32),
    'RGBX': (0x000000ff,0x0000ff00,0x00ff0000,0x00000000, 8,8,8,0, 32),

    'R': (0xff,0x00,0x00,0x00, 8,0,0,0, 8),
    'G': (0x00,0xff,0x00,0x00, 0,8,0,0, 8),
    'B': (0x00,0x00,0xff,0x00, 0,0,8,0, 8),
    'A': (0x00,0x00,0x00,0xff, 0,0,0,8, 8),
    'RGBAX': (0x000000ff,0x0000ff00,0x00ff0000,0xff000000, 8,8,8,8, 40),
    'RGBAXX': (0x000000ff,0x0000ff00,0x00ff0000,0xff000000, 8,8,8,8, 48),
}


for spec in RAWMODE_SPEC.values():
    validate_spec(spec)


def spec_to_rawmode(spec):
    """Returns the rawmode of a spec or None."""
    for r, s in RAWMODE_SPEC.items():
        if spec == s:
            return r
    return None


def rawmode_to_spec(rawmode):
    """Returns the spec of a rawmode or None."""
    return RAWMODE_SPEC.get(rawmode)


"""The spec used in official images that have flag 'RGB'."""
OFFICIAL_RGB_SPEC = RAWMODE_SPEC.get('BGR;16')


class StiImageDecoder(ImageFile.PyDecoder):
    """Decoder for images in a STI file."""

    # List of rawmodes supported by Pillow's raw_decoder.
    # Assumes mode RGBA when there is an A band, and mode RGB otherwise.
    RAWMODES = (
        'BGR;16', 'BGR;15', 'BGRA;15', 'RGBA;15', 'RGB;4B', 'RGBA;4B', # 16 bits
        'BGR', 'RGB', # 24 bits
        'ABGR', 'XBGR', 'ARGB', 'BGRA', 'BGRX', 'RGBA', # 32 bits
        'R', 'G', 'B', 'A', # 8 bits
        # XXX other rawmodes have problems
        #'RGBX', # (consistency problem) the X band is not set to 255 like the other cases
        #'XRGB', # (buffer problem?) wrongly listed as 24 bits
        #'RGBAX', # (version problem) needs Pillow>=5.3.0
        #'RGBAXX', # (version problem) needs Pillow>=5.3.0
    )

    def init(self, args):
        self.do = args[0]
        self.data = bytearray()
        self.bytes = 0
        if self.do == 'rgb':
            self.spec = args[1]
            self.bytes = args[2]
            validate_spec(self.spec)
            assert isinstance(self.bytes, int) and self.bytes >= 0, "number of bytes %r" % self.bytes
            assert self.mode in ['RGB', 'RGBA'], "mode %r" % self.mode
            self.depth = self.spec[-1]
            self.rawmode = spec_to_rawmode(self.spec)
        elif self.do == 'fill':
            self.color = args[1]
            assert [isinstance(x, int) and x >= 0 and x <= 255 for x in self.color] == [True] * len(self.mode), "fill color %r" % self.color
            assert self.mode in ['P', 'RGB', 'RGBA'], "mode %r" % self.mode
        elif self.do == 'indexes':
            self.bytes = args[1]
            assert isinstance(self.bytes, int) and self.bytes >= 0, "number of bytes %r" % self.bytes
            assert self.mode == 'P', "mode %r" % self.mode
        elif self.do == 'etrle':
            self.transparent = args[1]
            self.bytes = args[2]
            assert isinstance(self.transparent, int) and self.transparent == 0, "transparent index %r" % self.transparent # XXX etrle_decompress expects index 0
            assert isinstance(self.bytes, int) and self.bytes >= 0, "number of bytes %r" % self.bytes
            assert self.mode == "P", "mode %r" % self.mode
        else:
            raise NotImplementedError("decoder args {}".format(args))

    def decode(self, buffer):
        """Decodes buffer data as image pixels"""
        # gather the target amount of data
        if self.bytes > len(buffer):
            self.data.extend(buffer)
            self.bytes -= len(buffer)
            return len(buffer), 0 # get more data
        self.data.extend(buffer[:self.bytes])
        self.bytes = 0
        buffer = bytes(self.data)
        num_pixels = self.state.xsize * self.state.ysize
        # decode
        if self.do == 'rgb': # colors
            bytes_per_pixel = self.depth // 8
            assert len(buffer) == num_pixels * bytes_per_pixel, "data size %r" % len(buffer)
            if self.rawmode in self.RAWMODES: # fast C code
                try:
                    self.set_as_raw(buffer, rawmode=self.rawmode)
                    return -1, 1 # done
                except Exception as ex:
                    print("FIXME mode %r rawmode %r failed: %r" % (self.mode, self.rawmode, ex))
            # generic python fallback
            if bytes_per_pixel == 1:
                colors = struct.unpack("<{}B".format(num_pixels), buffer)
            elif bytes_per_pixel == 2:
                colors = struct.unpack("<{}H".format(num_pixels), buffer)
            elif bytes_per_pixel == 3:
                colors = struct.unpack("<" + "HB" * num_pixels, buffer)
                colors = [low + high << 16 for low, high in zip(colors[0::2], colors[1::2])]
            else:
                assert bytes_per_pixel >= 4 # masks are limited to 4 bytes so ignore the rest
                colors = struct.unpack("<" + "L{}x".format(bytes_per_pixel - 4) * num_pixels, buffer)
            assert len(colors) == num_pixels
            num_components = len(self.mode)
            buffer = bytes([x for color in colors for x in _color_components(color, self.spec)[:num_components]])
            self.set_as_raw(buffer)
            return -1, 1 # done
        elif self.do == 'fill': # color
            buffer = bytes(self.color * num_pixels)
            self.set_as_raw(buffer)
            return -1, 1 # done
        elif self.do == 'indexes': # uncompressed indexes
            self.set_as_raw(buffer)
            return -1, 1 # done
        elif self.do == 'etrle': # etrle compressed indexes
            buffer = bytes(etrle_decompress(self.data))
            self.set_as_raw(buffer)
            return -1, 1 # done
        raise NotImplementedError("do %r", self.do)


# XXX ImageFile.PyEncoder does not exist
class PyEncoder(object):
    """
    Python implementation of a format encoder.

    Override this class and add the encoding logic in the `encode` method.
    The encoder should be registered with:
    ```
    Image.register_encoder('name', MyEncoderClass)
    ```

    This class mimics the interface of ImagingEncoder excluding `encode_to_file`.
    """

    _pushes_fd = False

    def __init__(self, mode, *args):
        self.im = None
        self.state = ImageFile.PyCodecState()
        self.fd = None
        self.mode = mode
        self.init(args)

    def init(self, args):
        """
        Override to perform decoder specific initialization

        :param args: Array of args items from the tile entry
        :returns: None
        """
        self.args = args

    @property
    def pushes_fd(self):
        """True if this encoder expects to push directly to self.fd"""
        return self._pushes_fd

    def encode(self, bufsize=16384):
        """
        Override to encode data to a new buffer limited by bufsize.
        If errcode is 0, there is more data to encode.

        :param bufsize: Optional buffer size.
        :returns: A tuple of (bytes produced, errcode, buffer).
            Positive errcode means it is done.
            Negative errcode means an error from `ImageFile.ERRORS` occured.
        """
        raise NotImplementedError()

    def cleanup(self):
        """
        Override to perform encoder specific cleanup.

        :returns: None
        """
        pass

    def encode_to_pyfd(self):
        """
        Override to perform the encoding process to a python file-like object.
        The default implementation uses `encode` with the default buffer size.

        :returns: A tuple of (bytes produced, errcode).
            Positive errcode means it is done.
            Negative errcode means an error from `ImageFile.ERRORS` occured.
        """
        total_bytes = 0
        while True:
            num_bytes, errcode, buffer = self.encode()
            total_bytes += num_bytes
            self.fd.write(buffer)
            if errcode:
                return total_bytes, errcode

    def setimage(self, im, extents=None):
        """
        Set the core input image for the encoder.

        :param im: A core image object.
        :param extents: A 4 tuple of (x0, y0, x1, y1) defining the rectangle for this tile.
        :returns: None
        """
        self.im = im

        if extents:
            (x0, y0, x1, y1) = extents
        else:
            (x0, y0, x1, y1) = (0, 0, 0, 0)

        if x0 == 0 and x1 == 0:
            self.state.xsize, self.state.ysize = self.im.size
        else:
            self.state.xoff = x0
            self.state.yoff = y0
            self.state.xsize = x1 - x0
            self.state.ysize = y1 - y0

        if self.state.xsize <= 0 or self.state.ysize <= 0:
            raise ValueError("Size cannot be negative")

        if (self.state.xsize + self.state.xoff > self.im.size[0] or
           self.state.ysize + self.state.yoff > self.im.size[1]):
            raise ValueError("Tile cannot extend outside image")

    def setfd(self, fd):
        """
        Set the python file-like object.

        :param fd: A python file-like object
        :returns: None
        """
        self.fd = fd


class StiImageEncoder(PyEncoder):
    """
    Encoder for images in a STI file.

    ```
    img.tobytes(StiImagePlugin.format, 'colors', (spec,)) # defaults to official spec
    img.tobytes(StiImagePlugin.format, 'indexes')
    img.tobytes(StiImagePlugin.format, 'etrle')
    ```
    """

    # List of rawmodes supported by Pillow's raw_encoder.
    # Assumes mode RGBA when there is an A band, and mode RGB otherwise.
    RAWMODES = [
        'BGR', 'RGB', # 24 bits
        'ABGR', 'XBGR', 'XRGB', 'BGRA', 'BGRX', 'RGBA', # 32 bits
        'R', 'G', 'B', 'A', # 8 bits
        # XXX other rawmodes have problems
        #'RGBX', # (consistency problem) the X band is not set to 0 like the other cases
    ]

    def init(self, args):
        self.do = args[0]
        if self.do == 'colors':
            assert self.mode in ['RGB', 'RGBA']
            self.spec = args[1] or OFFICIAL_RGB_SPEC # default spec
            if isinstance(self.spec, str):
                self.rawmode = self.spec
                self.spec = rawmode_to_spec(self.rawmode)
            else:
                self.rawmode = spec_to_rawmode(self.spec)
            self.rawencoder = None
            validate_spec(self.spec)
            alpha_mask = self.spec[3]
            if alpha_mask == 0:
                self.mode = 'RGB' # force no alpha
            else:
                self.mode = 'RGBA' # force alpha
            self.bytes = bytearray()
            self.y = None
            self.x = None
        elif self.do == 'indexes':
            assert self.mode in ['P']
            self.x = None
            self.y = None
        elif self.do == 'etrle':
            assert self.mode in ['P']
            self.bytes = bytearray()
            self.x = None
            self.y = None
        else:
            raise NotImplementedError("do %r" % self.do)

    def encode(self, bufsize=16384):
        """
        Encode data to a new buffer limited by bufsize.
        If errcode is 0, there is more data to encode.

        :param bufsize: Optional buffer size.
        :returns: A tuple of (bytes produced, errcode, buffer).
            Positive errcode means it is done.
            Negative errcode means an error from `ImageFile.ERRORS` occured.
        """
        if self.do == 'colors':
            return self._encode_colors(bufsize)
        elif self.do == 'indexes':
            return self._encode_indexes(bufsize)
        elif self.do == 'etrle':
            return self._encode_etrle(bufsize)
        raise NotImplementedError("do %r" % self.do)

    def _encode_colors(self, bufsize):
        """Encode colors according to the spec."""
        assert self.mode in ['RGB', 'RGBA']
        if self.im.mode != self.mode:
            self.im = self.im.copy().convert(self.mode)
        if self.rawmode in self.RAWMODES:
            if self.rawencoder is None:
                self.rawencoder = Image._getencoder(self.mode, 'raw', (self.rawmode))
                self.rawencoder.setimage(self.im, self.state.extents())
            return self.rawencoder.encode(bufsize)
        pixel_access = self.im.pixel_access()
        depth = self.spec[8]
        x0, y0, x1, y1 = self.state.extents()
        for y in range(self.y or y0, y1):
            for x in range(self.x or x0, x1):
                if len(self.bytes) > bufsize:
                    self.y = y
                    self.x = x
                    buffer = bytes(self.bytes[:bufsize])
                    self.bytes = self.bytes[bufsize:]
                    return len(buffer), 0, buffer # there is more data
                color = pixel_access[x, y]
                data = _color_bytes(color, self.spec)
                self.bytes.extend(data)
            self.x = None
        else:
            self.y = y1
        if len(self.bytes) > bufsize:
            buffer = bytes(self.bytes[:bufsize])
            self.bytes = self.bytes[bufsize:]
            return len(buffer), 0, buffer # there is more data
        buffer = bytes(self.bytes)
        self.bytes = self.bytes[:0]
        return len(buffer), 1, buffer # done

    def _encode_indexes(self, bufsize):
        """Copy palette indexes."""
        assert self.mode == 'P'
        assert self.im.mode == 'P'
        pixel_access = self.im.pixel_access()
        buffer = bytearray()
        x0, y0, x1, y1 = self.state.extents()
        for y in range(self.y or y0, y1):
            for x in range(self.x or x0, x1):
                if bufsize <= len(buffer):
                    self.y = y
                    self.x = x
                    return len(buffer), 0, buffer # there is more data
                index = pixel_access[x, y]
                buffer.append(index)
            self.x = None
        return len(buffer), 1, buffer # done

    def _encode_etrle(self, bufsize):
        """Encode palette indexes with ETRLE."""
        assert self.mode == 'P'
        assert self.im.mode == 'P'
        pixel_access = self.im.pixel_access()
        buffer = bytearray()
        x0, y0, x1, y1 = self.state.extents()
        for y in range(self.y or y0, y1):
            if len(self.bytes) > bufsize:
                buffer = bytes(self.bytes[:bufsize])
                self.bytes = self.bytes[bufsize:]
                self.y = y
                return len(buffer), 0, buffer # there is more data
            # process a complete line
            line = bytearray()
            for x in range(x0, x1):
                index = pixel_access[x, y]
                line.append(index)
            while len(line) > 0:
                control = 0 # uncompressed
                n = len(line)
                for i in range(1,n):
                    # lone 0's that can increase the size are left uncompressed
                    if line[i] != 0:
                        continue
                    if line[i-1] != 0:
                        if i+1 == n:
                            n -= 1 # uncompressed length, next cycle is compressed (lone 0 at the end)
                            break
                        continue
                    if i == 1: # [0, 0, ...]
                        control = 0x80 # compressed
                        for i in range(2,n):
                            if line[i] != 0:
                                n = i
                                break
                    else:
                        n = i-1 # uncompressed length, next cycle is compressed
                    break
                else:
                    if n == 1 and line[0] == 0:
                        control = 0x80 # compressed, lone 0 at the end
                n = min(n, 0x7f) # respect maximum length
                # encode
                assert control in [0, 0x80]
                assert n >= 1 and n <= 0x7f
                self.bytes.append(control | n)
                if control == 0:
                    self.bytes.extend(line[:n])
                line = line[n:]
            self.bytes.append(0) # end of line, control with length 0
        else:
            self.y = y1
        if len(self.bytes) > bufsize:
            buffer = bytes(self.bytes[:bufsize])
            self.bytes = self.bytes[bufsize:]
            return len(buffer), 0, buffer # there is more data
        buffer = bytes(self.bytes)
        self.bytes = self.bytes[len(self.bytes):]
        return len(buffer), 1, buffer # done


# register STI image plugin
Image.register_decoder(StiImagePlugin.format, StiImageDecoder)
Image.register_encoder(StiImagePlugin.format, StiImageEncoder)
Image.register_open(StiImagePlugin.format, StiImagePlugin, lambda x: len(x) >= 4 and x[:4] == b'STCI')
Image.register_save(StiImagePlugin.format, StiImagePlugin._save_handler)
Image.register_save_all(StiImagePlugin.format, StiImagePlugin._save_all_handler)
Image.register_extension(StiImagePlugin.format, '.sti')
Image.register_mime(StiImagePlugin.format, 'image/x-stci')

