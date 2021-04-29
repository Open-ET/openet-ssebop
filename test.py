"""This script provides a quick way to test issues that are going wrong in a ipynb in the examples folder
without having to throw 'pip install . --no-deps' every time you want to print something or troubleshoot."""
import openet.ssebop as model
# Import the Earth Engine package
import ee


try:
    ee.Initialize()
    print('worked')
except ee.EEException:
    print('trying a second time')
    ee.Authenticate()
    ee.Initialize()

ndvi_palette = ['#EFE7E1', '#003300']
et_palette = [
    'DEC29B', 'E6CDA1', 'EDD9A6', 'F5E4A9', 'FFF4AD', 'C3E683', '6BCC5C',
    '3BB369', '20998F', '1C8691', '16678A', '114982', '0B2C7A']
viridis_palette = ['440154', '433982', '30678D', '218F8B', '36B677', '8ED542', 'FDE725']

image_size = 768

# Salinas
# landsat_img = ee.Image('LANDSAT/LC08/C02/T1_L2/LC08_043035_20160722')
# Wilcox
# landsat_img = ee.Image('LANDSAT/LC08/C02/T1_L2/LC08_035037_20160714')
# Viginia
# landsat_img = ee.Image('LANDSAT/LC08/C02/T1_L2/LC08_016033_20160725')
# x = 'LC08_035037_20160714'
x = 'LC08_043035_20160722'
landsat_img = ee.Image(f'LANDSAT/LC08/C02/T1_L2/{x}')
landsat_crs = landsat_img.select('SR_B3').projection().getInfo()['crs']
landsat_region = landsat_img.geometry().bounds(1, 'EPSG:4326')
landsat_dt = ee.Date(landsat_img.get('system:time_start'))

# # Build the SSEBop object from the Landsat image
# model_obj = model.Image.from_landsat_c2_sr(
#     landsat_img,
#     tcorr_source='SCENE_GRIDDED',
#     et_reference_source='IDAHO_EPSCOR/GRIDMET',
#     et_reference_band='etr',
#     et_reference_factor=0.85,
#     et_reference_resample='nearest',
#     tmax_source='projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010_elr'
# )

## ============== NON-Lapse Rate Adjusted =================
# Build the SSEBop object from the Landsat image
model_obj = model.Image.from_landsat_c2_sr(
    landsat_img,
    tcorr_source='SCENE_GRIDDED',
    et_reference_source='IDAHO_EPSCOR/GRIDMET',
    et_reference_band='etr',
    et_reference_factor=0.85,
    et_reference_resample='nearest',
    tmax_source='projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010'
)


et_property = model_obj.et_fraction