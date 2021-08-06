"""
This is a temporary script to fascilitate the conversion of TiffStacks from micromanager2-gamma to zarr

"""

from pycromanager import Bridge
import zarr
import os
import time

bridge = Bridge(convert_camel_case=False)

mm = bridge.get_studio()

dm = mm.getDisplayManager()

dv = dm.getAllDataViewers().get(0)

dp = dv.getDataProvider()

print("Generating coordinate set based on max indicies")
# data provider can return the maximum number of each dimension in this dataset
# each coordinate is (P, T, C, Z, Y, X)
# max_coord = dp.getMaxIndicies()
# max_p = max_coord.getP()
# max_t = max_coord.getT()
# max_c = max_coord.getC()
# max_z = max_coord.getZ()
max_p = dp.getNextIndex('position')
max_t = dp.getNextIndex('time')
max_c = dp.getNextIndex('channel')
max_z = dp.getNextIndex('z')
coordset = set()
for p in range(max_p):
    for t in range(max_t):
        for c in range(max_c):
            for z in range(max_z):
                coordset.add((p, t, c, z))
print(f"num of images/coordinates in coordset = {len(coordset)}")

# load target zarr array
target = 'X:\\rawdata\\hummingbird\\Janie\\2021_07_29_LiveHEK_NoPerf_63x_09NA\\Endpoint\\Endpoint_TimeLapse_1_zarr\\'
pregen_zarr = 'test.zarr'
src = os.path.join(target, pregen_zarr)
print("opening pre-generated zarr array")
z = zarr.open(src, mode='r+')
print(f"zarr loaded and shape = {z.shape}")
# z.shape = (16, 20, 4, 77, 2k, 2k)


# loop through all coordinates, construct a coordinate object and pass that to retrieve a coordinate
# CoordBuilder = max_coord.copyBuilder()
random_coord = dp.getAnyImage().getCoords()

print("looping through coordinates, fetching data from micromanager, then writing data to array")
# loop through coordset, for each item in the set, build a coordinate, fetch the image, place image in array
count = 0
start = time.time()
for c in coordset:
    if count % 100 == 0:
        chkpoint = time.time()
        print(f'writing image number {count} at coordinate {c}')
        print(f'\t time elapsed = {chkpoint-start}')
        print(f'\t average time per image = {(chkpoint-start)/count}')
    count += 1
    CoordBuilder = random_coord.copyBuilder()
    CoordBuilder.p = c[0]
    CoordBuilder.t = c[1]
    CoordBuilder.c = c[2]
    CoordBuilder.z = c[3]
    mm_coord = CoordBuilder.build()
    im = dp.getImage(mm_coord)
    z[c[0], c[1], c[2], c[3]] = im.getRawPixels().reshape((2048, 2048))

# CoordBuilder.p = 1
# CoordBuilder.t = 1
# CoordBuilder.z = 1
# CoordBuilder.c = 1
# coord = CoordBuilder.build()
#
# im = dp.getImage(coord)
#
# z[1, 1, 1, 1] = im.getRawPixels().reshape((2048, 2048))

dm2 = mm.getDisplayManager()
dv2 = dm2.getAllDataViewers().get(0)
dp2 = dv2.getDataProvider()
max_coord = dp2.getMaxIndicies()
print(max_coord)