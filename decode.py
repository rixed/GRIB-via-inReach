# requirements:
# $ python -m venv $PWD/venv
# $ source venv/bin/activate
# $ pip install pygrib cfgrib numpy pandas xarray
# $ apt-get install libeccodes-tools
# Maybe:
# $ patch venv/lib/python3.9/site-packages/gribapi/bindings.py eccodes.patch
import argparse

from codec import decode


def read_parts(filenames):
    """
    Reconstruct the messages from the given filenames.
    Actually concatenate it all, assuming the first one is indeed the first,
    and then split it at messages boundary and then reorder them properly.
    So other parts of the message can be added in any order.
    """
    assert len(filenames) > 0
    text = ''
    for filename in filenames:
        with open(filename, 'r') as f:
            text += f.read()
    #print(f"full message:\n{text}")
    text = [
        line.strip()
        for line in text.split('\n')
        if len(line) > 0 and line != 'END' ]
    assert len(text) >= 6
    part0 = "\n".join(text[:6])
    parts = [ "\n".join(text[i:i+2]) for i in range(6, len(text), 2) ]
    def part_number(part):
        part_no, _shift = part.split("\n")[0].split(',')
        return int(part_no)
    parts = [ part0 ] + sorted(parts, key=part_number)
    return parts


def main():
    parser = argparse.ArgumentParser(
        prog='Grib Decoder',
        description='Decode a compressed grib file received via SMS')
    parser.add_argument('-o', '--output',
        type=str,
        default='output.grib',
        help='Name of the created grib files (numeric suffix will be added)')
    parser.add_argument('filename',
        type=str,
        default=['/dev/stdin'],
        help='Input message(s)',
        nargs='*')

    args = parser.parse_args()
    print(f"output={args.output}, inputs={args.filename}")

    parts = read_parts(args.filename)
    decode(parts, args.output)

main()
