import os
import cfgrib
import numpy as np
import pandas as pd
import xarray as xr

CONST_MAX_SHIFT = 10
CONST_MAX_MSG_SIZE = 120

# Characters that can (almost) safely be sent via inReach:
CONST_CHARS = """!"#$%\'()*+,-./:;<=>?_¡£¥¿&¤0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÄÅÆÇÉÑØøÜßÖàäåæèéìñòöùüΔΦΓΛΩΠΨΣΘΞ"""
# To get a full range of 128 code possibilities, these are extra two character
# codes:
CONST_EXTRACHARS = [ '@!', '@@', '@#', '@$', '@%', '@?' ]

assert len(CONST_CHARS) + len(CONST_EXTRACHARS) == 128

def chars_of_shift(shift):
    return CONST_CHARS[shift:] + CONST_CHARS[:shift]

#
# Encoder
#

def next_part(part_no, bin_data, consumed, timepoints, latmin, latmax, lonmin, lonmax, latdiff, londiff, gribtime, shift):
    # This function encodes the GRIB binary data into characters that can be
    # sent over the inReach.
    new_chars = chars_of_shift(shift)

    def encoder(x):
        # This encodes a byte into the coding scheme based on the SHIFT.
        if len(x) < 7:
            x = x + '0'*(7-len(x))
        dec = int(x, 2)
        if dec < 122:
            return new_chars[dec]
        else:
            return CONST_EXTRACHARS[dec - 122]

    part = ''
    # First the global header:
    if part_no == 0:
        hours = ",".join((timepoints/np.timedelta64(1, 'h')).astype('int').astype('str'))
        part += f"""{hours}
{gribtime}
{latmin},{latmax},{lonmin},{lonmax}
{latdiff},{londiff}
{shift}
"""
    else:
        part += f"{part_no},{shift}\n"
    # Then some vector values:
    while len(part) < CONST_MAX_MSG_SIZE and consumed < len(bin_data):
        byte = bin_data[consumed:consumed+7]
        part += encoder(byte)
        consumed += 7
    part += "\n"
    if consumed >= len(bin_data):
        part += "END"
    return part, consumed


def to_binary_byte(x):
    return "{0:04b}".format(x)


def encode(grib_file, send_part):
    """
    Encode the given GRIB file into fragments suitable to be sent via SMS.
    send_part is given each fragment in turn, and should return False if the
    send fails, in which case the fragment will be retried with a different
    encoding (shift).

    Returns True if the message could be sent.
    """
    grib = xr.open_dataset(grib_file).to_dataframe()

    timepoints = grib.index.get_level_values(0).unique()
    lats = grib.index.get_level_values(1).unique()
    lons = grib.index.get_level_values(2).unique()
    latmin = lats.min()
    latmax = lats.max()
    lonmin = lons.min()
    lonmax = lons.max()

    # This is the difference between each lat/lon point.
    latdiff = pd.Series(lats).diff().dropna().round(6).unique()
    londiff = pd.Series(lons).diff().dropna().round(6).unique()

    if len(latdiff) > 1 or len(londiff) > 1:
        print('Irregular point separations!')

    gribtime = grib['time'].iloc[0]

    # This grabs the U-component and V-component of wind speed, calculates the
    # magnitude in kts, rounds to the nearest 5kt speed, and converts to binary.
    mag = (np.sqrt(grib['u10']**2 + grib['v10']**2)*1.94384/5).round().astype('int').clip(upper=15).apply(to_binary_byte).str.cat()
    # This encodes the wind direction into 16 cardinal directions and converts
    # to binary.
    dirs = (((round(np.arctan2(grib['v10'], grib['u10']) / (2 * np.pi / 16))) + 16) % 16).astype('int').apply(to_binary_byte).str.cat()
    # bin_data is a string of 0 and 1 encoding the low-res U/V values
    bin_data = mag + dirs

    # Due to Garmin's inability to send certain character combinations (such
    # as ">f" if I recall), this shift attempts to try different encoding schemes.
    shift = 0
    part_no = 0
    consumed = 0
    while shift <= CONST_MAX_SHIFT and consumed < len(bin_data):
        part, new_consumed = next_part(part_no, bin_data, consumed, timepoints, latmin, latmax, lonmin, lonmax, latdiff[0], londiff[0], gribtime, shift)
        if send_part(part):
            # Success
            part_no += 1
            shift = 0  # reset shift to 0
            consumed = new_consumed
        else:
            # Failure, try with another shift:
            shift += 1
    return (shift < CONST_MAX_SHIFT)


def just_print(part):
    print(part, end="")
    return True


def ignore(part):
    return True


#
# Decoder
#

def decode_msg(x, shift):
    new_chars = chars_of_shift(shift)
    decoded = []
    counter = 0
    while counter < len(x):
        if x[counter] == '@':
            decoded.append("{0:07b}".format(CONST_EXTRACHARS.index(x[counter:counter+2])))
            counter += 2
        else:
            decoded.append("{0:07b}".format(new_chars.index(x[counter])))
            counter += 1
    #print(f"decoded={decoded}")
    decoded = ''.join(decoded)
    return decoded


def to_ints(lst):
    return [ int(x) for x in lst ]


def to_floats(lst):
    return [ float(x) for x in lst ]


def reindex(data, hours, latitude, longitude):
    assert len(data) == len(hours) * len(latitude) * len(longitude), f"{len(data)=}!={len(hours)}*{len(latitude)}*{len(longitude)}"
    i = 0
    x = []
    for h in range(len(hours)):
        x.append([])
        for lat in range(len(latitude)):
            x[h].append([])
            for lon in range(len(longitude)):
                x[h][lat].append(data[i])
                i += 1
    return x


def decode(parts, grib_file):
    """
    Decode the GRIB encoded in the parts and store it in the given file.
    """
    assert len(parts)>0
    # First part must contain the global header:
    part0 = parts[0].split("\n")
    hours = part0[0].split(',')
    gribdate, gribtime = part0[1].split(" ")
    latmin, latmax, lonmin, lonmax = to_floats(part0[2].split(','))
    latdiff, londiff = to_floats(part0[3].split(','))
    decoded = ''
    for part_no, part in enumerate(parts):
        if part_no == 0:
            shift = int(part0[4])
            data = part0[5:]
        else:
            lines = part.split("\n")
            part_no, shift = to_ints(lines[0].split(","))
            data = lines[1:]
        while data[-1] == "END" or data[-1] == "":
            data = data[:-1]
        decoded += decode_msg(''.join(data), shift)
    # Now build the dataframe:
    decoded = [decoded[i:i+4] for i in range(0, len(decoded), 4)]
    if len(decoded[-1]) < 4:
        del decoded[-1]
    decoded = [int(i, 2) for i in decoded]
    half_len = int(len(decoded)/2)
    mag = pd.Series(decoded[:half_len])
    dirs = pd.Series(decoded[half_len:]).reset_index(drop=True)

    mag = mag*5/1.94384
    v10 = np.sin(2*np.pi*dirs/16)*mag
    u10 = np.cos(2*np.pi*dirs/16)*mag

    # Create a sample DataFrame with one array of values
    longitude = np.linspace(lonmin, lonmax, 1 + int(round((lonmax-lonmin)/londiff)), endpoint=True)
    latitude = np.linspace(latmin, latmax, 1 + int(round((latmax-latmin)/latdiff)), endpoint=True)
    #print(f"lon:{len(longitude)}")
    #print(f"lat:{len(latitude)}")
    #print(f"v10:{len(v10)}, u10:{len(u10)}")
    # Make v10 and u10 per hour and "square":
    v10 = reindex(v10, hours, latitude, longitude)
    u10 = reindex(u10, hours, latitude, longitude)
    #print(f"v10={v10}")
    # Define the projection information
    proj_info = {
        'grid_type': 'regular_ll',
        'latitude_of_first_grid_point': latitude[0],
        'longitude_of_first_grid_point': longitude[0],
        'latitude_of_last_grid_point': latitude[-1],
        'longitude_of_last_grid_point': longitude[-1],
        'Nj': len(latitude),
        'Ni': len(longitude),
        # does not appear to do anything:
    #    'parameterCategory': 2,  # Parameter category for wind (2)
    #    'parameterNumber': 2,   # Parameter number for wind direction (2)
    }

    # Create an xarray dataset with the vector data.
    # Using hours as a 3rd index does not work.
    # Writing the different hours successively does not work either.
    # We are going to concatenate the files to embed all the hours.
    try:
        os.remove(grib_file)
    except FileNotFoundError:
        pass
    for h in range(len(hours)):
        ds = xr.Dataset({
            'u10': (['latitude', 'longitude'], u10[h]),
            'v10': (['latitude', 'longitude'], v10[h]),
        }, coords={
            'longitude': longitude,
            'latitude': latitude,
        }, attrs=proj_info)

        # Does not appear to do anything either:
        #ds['u10'].attrs['parameterNumber'] = 2 # GRB_WIND_VX
        #ds['v10'].attrs['parameterNumber'] = 3 # GRB_WIND_VY
        #ds['u10']['P2'] = hours[h]
        #ds['v10']['P2'] = hours[h]

        tmp_file = grib_file + ".tmp"
        from cfgrib.xarray_to_grib import to_grib
        to_grib(ds, tmp_file)

        # Now reopen it to set the proper parameterNumber/Category and times
        import pygrib
        grbs = pygrib.open(tmp_file)
        grb1 = grbs.message(1)
        grb1['parameterCategory'] = 2
        grb1['parameterNumber'] = 2

        grb2 = grbs.message(2)
        grb2['parameterCategory'] = 2
        grb2['parameterNumber'] = 3

        for grb in [grb1, grb2]:
            ## Still no luck: Can only change existing key
            # grb['P1'] = 0
            # grb['P2'] = hours[h]
            # grb['unitOfTimeRange'] = 1

            # At least set the time right:
            grb['dataDate'] = int(gribdate.replace('-', ''))
            gh, gm, _ = gribtime.split(':')
            gh = str(int(gh) + int(hours[h]))
            grb['dataTime'] = int(gh + gm)

        grib_with_hour = grib_file + f".{hours[h]}"
        with open(grib_with_hour, 'wb+') as f:
            f.write(grb1.tostring())
            f.write(grb2.tostring())

        print(f"GRIB files saved into {grib_with_hour}.")





def test_decode():
    parts = [
"""12,24,36,48
2023-08-30 12:00:00
25.0,43.0,-29.0,-7.0
2.0,2.0
0
&nåO&nà7&nåN=nh7&nå6+*fN&nß>+%f7&j77<f9P¿jd==.èe*b!6=rd7=
""",
"""1,0
*78¤!fP&jf6"o(O&%fN&nà8=nà7=.fN*jf7=*f=<fd==*7><bf8&%f6*fhN<%9="*à==*f7+.97==(N*nå8&nhN&nhO&*à7=.åO<ff7=*å5+*77+.à=<
""",
"""2,0
ff7&n7=*f9O5f#7=*h=!fhO&*d==*å7¿"*e=nà8=o*8=jå?=nhO=%B8=%f7<ff7<få7<f9>=.ß="*f6=b5>=nà7<f78&nd=*%9O&fM¿nåyXü7=¤oF@@Δ
""",
"""3,0
X7O¤wΛhæfß¡WÉYFæwFΣXßÄM1wK0ΘNÑwGåS,gDΓΞnüjf6)Σ&b*jd!)@@;&nßQnΣ@%=&nåyØ$ß=&oK-(WßMFÑ"någBwXù&.@!vùΞdW¡UWåODÆΘ$@@Çåj!"
""",
"""4,0
*b4É'K¿"*f4Ξn7QGÑSs¿oFwYΣÑ?¤wJΞüWåQVÉΓbåfñOWÑMléÉñ&nñÉ"ùùO¤ALa@?@%ΨT"Åå@#"@%é7wnåΣ5tnß=+ùSØ*f7=Hü#?¿nìΞc?ßO0xO!ΣXåyH
""",
"""5,0
åSHègΛUnèÉñöüWÆvD@?Uo@?@?7Rgü&nüc.òùΣWÑ!
END
""" ]
    decode(parts, "/tmp/test_decode.grib")

def test_encode():
    encode('gfs20230830190103925.grb', just_print)

#test_decode()
#encode('gfs20230830190103925.grb', just_print)
