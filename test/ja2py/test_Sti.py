import unittest
from PIL import ImagePalette
from .fixtures import *
from ja2py.fileformats import Sti16BitHeader, Sti8BitHeader, StiHeader, StiSubImageHeader, AuxObjectData,\
                              is_16bit_sti, is_8bit_sti, load_16bit_sti, load_8bit_sti
from ja2py.content import Image16Bit, Images8Bit


class TestSti16BitHeader(unittest.TestCase):
    def test_size(self):
        self.assertEqual(Sti16BitHeader.get_size(), 20)

    def test_read_from_bytes(self):
        test_bytes = (b'\x01\x00\x00\x00' + b'\x02\x00\x00\x00' + b'\x03\x00\x00\x00' + b'\x04\x00\x00\x00' +
                      b'\x05' + b'\x06' + b'\x07' + b'\x08')

        header = Sti16BitHeader.from_bytes(test_bytes)

        self.assertEqual(header['red_color_mask'], 1)
        self.assertEqual(header['green_color_mask'], 2)
        self.assertEqual(header['blue_color_mask'], 3)
        self.assertEqual(header['alpha_channel_mask'], 4)
        self.assertEqual(header['red_color_depth'], 5)
        self.assertEqual(header['green_color_depth'], 6)
        self.assertEqual(header['blue_color_depth'], 7)
        self.assertEqual(header['alpha_channel_depth'], 8)

    def test_write_to_bytes(self):
        header = Sti16BitHeader(
            red_color_mask=8,
            green_color_mask=7,
            blue_color_mask=6,
            alpha_channel_mask=5,
            red_color_depth=4,
            green_color_depth=3,
            blue_color_depth=2,
            alpha_channel_depth=1
        )
        expected = (b'\x08\x00\x00\x00' + b'\x07\x00\x00\x00' + b'\x06\x00\x00\x00' + b'\x05\x00\x00\x00' +
                    b'\x04' + b'\x03' + b'\x02' + b'\x01')

        self.assertEqual(bytes(header), expected)

    def test_idempotency(self):
        field_values = {
            'red_color_mask': 1231,
            'green_color_mask': 7121,
            'blue_color_mask': 1235,
            'alpha_channel_mask': 1235,
            'red_color_depth': 25,
            'green_color_depth': 3,
            'blue_color_depth': 1,
            'alpha_channel_depth': 123
        }
        header = Sti16BitHeader(**field_values)

        regenerated_header = Sti16BitHeader.from_bytes(bytes(header))

        for key, value in field_values.items():
            self.assertEqual(regenerated_header[key], value)


class TestSti8BitHeader(unittest.TestCase):
    def test_size(self):
        self.assertEqual(Sti8BitHeader.get_size(), 20)

    def test_read_from_bytes(self):
        test_bytes = b'\x01\x00\x00\x00' + b'\x02\x00' + b'\x03' + b'\x04' + b'\x05' + (11 * b'\x00')

        header = Sti8BitHeader.from_bytes(test_bytes)

        self.assertEqual(header['number_of_palette_colors'], 1)
        self.assertEqual(header['number_of_images'], 2)
        self.assertEqual(header['red_color_depth'], 3)
        self.assertEqual(header['green_color_depth'], 4)
        self.assertEqual(header['blue_color_depth'], 5)

    def test_write_to_bytes(self):
        header = Sti8BitHeader(
            number_of_palette_colors=5,
            number_of_images=4,
            red_color_depth=3,
            green_color_depth=2,
            blue_color_depth=1
        )
        expected = b'\x05\x00\x00\x00' + b'\x04\x00' + b'\x03' + b'\x02' + b'\x01' + (11 * b'\x00')

        self.assertEqual(bytes(header), expected)

    def test_idempotency(self):
        field_values = {
            'number_of_palette_colors': 25,
            'number_of_images': 12,
            'red_color_depth': 66,
            'green_color_depth': 3,
            'blue_color_depth': 1
        }
        header = Sti8BitHeader(**field_values)

        regenerated_header = Sti8BitHeader.from_bytes(bytes(header))

        for key, value in field_values.items():
            self.assertEqual(regenerated_header[key], value)


class TestStiHeader(unittest.TestCase):
    def test_size(self):
        self.assertEqual(StiHeader.get_size(), 64)

    def test_read_from_bytes(self):
        test_bytes = (b'TEST' + b'\x01\x00\x00\x00' + b'\x02\x00\x00\x00' + b'\x03\x00\x00\x00' + b'\x04\x00\x00\x00' +
                      b'\x05\x00' + b'\x06\x00' + b'a' + 18 * b'\x01' + b'b' + b'\x07' + b'\x00' * 3 +
                      b'\x08\x00\x00\x00' + 12 * b'\x00')

        header = StiHeader.from_bytes(test_bytes)

        self.assertEqual(header['file_identifier'], b'TEST')
        self.assertEqual(header['initial_size'], 1)
        self.assertEqual(header['size_after_compression'], 2)
        self.assertEqual(header['transparent_color'], 3)
        self.assertEqual(header['flags'], 4)
        self.assertEqual(header['height'], 5)
        self.assertEqual(header['width'], 6)
        self.assertEqual(header['format_specific_header'], b'a' + 18 * b'\x01' + b'b')
        self.assertEqual(header['color_depth'], 7)
        self.assertEqual(header['aux_data_size'], 8)

    def test_write_to_bytes(self):
        header = StiHeader(
            file_identifier=b'STSI',
            initial_size=8,
            size_after_compression=7,
            transparent_color=6,
            flags=5,
            height=4,
            width=3,
            format_specific_header=b'b' + 18 * b'\x01' + b'a',
            color_depth=2,
            aux_data_size=1,
        )
        expected = (b'STSI' + b'\x08\x00\x00\x00' + b'\x07\x00\x00\x00' + b'\x06\x00\x00\x00' + b'\x05\x00\x00\x00' +
                    b'\x04\x00' + b'\x03\x00' + b'b' + 18 * b'\x01' + b'a' + b'\x02' + b'\x00' * 3 +
                    b'\x01\x00\x00\x00' + 12 * b'\x00')

        self.assertEqual(bytes(header), expected)

    def test_flags(self):
        header = StiHeader(flags=0)

        header.set_flag('flags', 'RGB', True)
        self.assertEqual(header['flags'], 4)

        header.set_flag('flags', 'INDEXED', True)
        self.assertEqual(header['flags'], 12)

        header.set_flag('flags', 'ZLIB', True)
        self.assertEqual(header['flags'], 28)

        header.set_flag('flags', 'ETRLE', True)
        self.assertEqual(header['flags'], 60)

    def test_idempotency(self):
        field_values = {
            'file_identifier': b'WRST',
            'initial_size': 123112,
            'size_after_compression': 3213,
            'transparent_color': 31,
            'flags': 6,
            'height': 12,
            'width': 11,
            'format_specific_header': b'c' + 18 * b'\x12' + b'd',
            'color_depth': 22,
            'aux_data_size': 9,
        }
        header = StiHeader(**field_values)

        regenerated_header = StiHeader.from_bytes(bytes(header))

        for key, value in field_values.items():
            self.assertEqual(regenerated_header[key], value)


class TestStiSubImageHeader(unittest.TestCase):
    def test_size(self):
        self.assertEqual(StiSubImageHeader.get_size(), 16)

    def test_read_from_bytes(self):
        test_bytes = b'\x01\x00\x00\x00' + b'\x02\x00\x00\x00' + b'\x03\x00' + b'\x04\x00' + b'\x05\x00' + b'\x06\x00'

        header = StiSubImageHeader.from_bytes(test_bytes)

        self.assertEqual(header['offset'], 1)
        self.assertEqual(header['length'], 2)
        self.assertEqual(header['offset_x'], 3)
        self.assertEqual(header['offset_y'], 4)
        self.assertEqual(header['height'], 5)
        self.assertEqual(header['width'], 6)

    def test_write_to_bytes(self):
        header = StiSubImageHeader(
            offset=6,
            length=5,
            offset_x=4,
            offset_y=3,
            height=2,
            width=1
        )
        expected = b'\x06\x00\x00\x00' + b'\x05\x00\x00\x00' + b'\x04\x00' + b'\x03\x00' + b'\x02\x00' + b'\x01\x00'

        self.assertEqual(bytes(header), expected)

    def test_idempotency(self):
        field_values = {
            'offset': 255,
            'length': 127,
            'offset_x': 66,
            'offset_y': 33,
            'height': 31,
            'width': 1
        }
        header = StiSubImageHeader(**field_values)

        regenerated_header = StiSubImageHeader.from_bytes(bytes(header))

        for key, value in field_values.items():
            self.assertEqual(regenerated_header[key], value)


class TestAuxObjectData(unittest.TestCase):
    def test_size(self):
        self.assertEqual(AuxObjectData.get_size(), 16)

    def test_read_from_bytes(self):
        test_bytes = b'\x01' + b'\x02' + b'\x03\x00' + 3 * b'\x00' + b'\x04' + b'\x05' + b'\x06' + 6 * b'\x00'

        header = AuxObjectData.from_bytes(test_bytes)

        self.assertEqual(header['wall_orientation'], 1)
        self.assertEqual(header['number_of_tiles'], 2)
        self.assertEqual(header['tile_location_index'], 3)
        self.assertEqual(header['current_frame'], 4)
        self.assertEqual(header['number_of_frames'], 5)
        self.assertEqual(header['flags'], 6)

    def test_write_to_bytes(self):
        header = AuxObjectData(
            wall_orientation=6,
            number_of_tiles=5,
            tile_location_index=4,
            current_frame=3,
            number_of_frames=2,
            flags=1
        )
        expected = b'\x06' + b'\x05' + b'\x04\x00' + 3 * b'\x00' + b'\x03' + b'\x02' + b'\x01' + 6 * b'\x00'

        self.assertEqual(bytes(header), expected)

    def test_idempotency(self):
        field_values = {
            'wall_orientation': 255,
            'number_of_tiles': 127,
            'tile_location_index': 66,
            'current_frame': 33,
            'number_of_frames': 31,
            'flags': 1
        }
        header = AuxObjectData(**field_values)

        regenerated_header = AuxObjectData.from_bytes(bytes(header))

        for key, value in field_values.items():
            self.assertEqual(regenerated_header[key], value)


class TestIsStiFormat(unittest.TestCase):
    funcs = [
        is_16bit_sti,
        is_8bit_sti,
    ]
    truthy_values = {
        create_non_image_buffer: None,
        create_16_bit_sti: is_16bit_sti,
        create_8_bit_sti: is_8bit_sti,
        create_8_bit_multi_image_sti: is_8bit_sti,
        create_8_bit_animated_sti: is_8bit_sti,
    }

    def test_sti_formats(self):
        for create_fn, expected_truthy_fn in self.truthy_values.items():
            truthy_fns = list(filter(lambda f: f(create_fn()), self.funcs))
            self.assertEqual(truthy_fns, [expected_truthy_fn] if expected_truthy_fn else [])


class TestLoad16BitSti(unittest.TestCase):
    def test_not_a_16_bit_sti(self):
        with self.assertRaises(ValueError):
            load_16bit_sti(create_non_image_buffer())

    def test_returns_16_bit_image(self):
        img = load_16bit_sti(create_16_bit_sti())
        self.assertIsInstance(img, Image16Bit)

    def test_dimensions(self):
        img = load_16bit_sti(create_16_bit_sti())

        self.assertEqual(img.width, 3)
        self.assertEqual(img.height, 2)

    def test_image_data(self):
        img = load_16bit_sti(create_16_bit_sti())

        self.assertEqual(img.image.tobytes(), b'PH\x88P\x88\x98P\xc8\xa8X\x08\xb8`\x08\xc8`L\x08')


class TestLoad8BitSti(unittest.TestCase):
    def test_not_a_8_bit_sti(self):
        with self.assertRaises(ValueError):
            load_8bit_sti(create_non_image_buffer())

    def test_returns_8bit_images(self):
        img = load_8bit_sti(create_8_bit_multi_image_sti())
        self.assertIsInstance(img, Images8Bit)

    def test_palette(self):
        img = load_8bit_sti(create_8_bit_multi_image_sti())
        self.assertIsInstance(img.palette, ImagePalette.ImagePalette)

    def test_len_single(self):
        img = load_8bit_sti(create_8_bit_sti())
        self.assertEqual(len(img), 1)

    def test_len_multi(self):
        img = load_8bit_sti(create_8_bit_multi_image_sti())
        self.assertEqual(len(img), 2)

    def test_offsets(self):
        img = load_8bit_sti(create_8_bit_multi_image_sti())
        self.assertEqual(img.images[0].offsets, (0, 0))
        self.assertEqual(img.images[1].offsets, (1, 2))

    def test_colors(self):
        img = load_8bit_sti(create_8_bit_multi_image_sti())
        self.assertEqual(img.images[0].image.convert('RGB').getpixel((0, 0)), (1, 2, 3))

    def test_aux_object_data(self):
        img = load_8bit_sti(create_8_bit_animated_sti())

        self.assertEqual(img.images[0].aux_data, {
            'wall_orientation': 0,
            'number_of_tiles': 1,
            'tile_location_index': 2,
            'current_frame': 0,
            'number_of_frames': 2,
        })
        self.assertEqual(img.images[1].aux_data, {
            'wall_orientation': 0,
            'number_of_tiles': 1,
            'tile_location_index': 2,
            'current_frame': 1,
            'number_of_frames': 0,
        })



