
# Code snipped for changing the Tcorr index
coll_id_list = [
    [4, 'projects/earthengine-legacy/assets/projects/usgs-ssebop/tcorr_scene/daymet_median_v2_monthly'],
    [6, 'projects/earthengine-legacy/assets/projects/usgs-ssebop/tcorr_scene/daymet_median_v2_annual'],
    [7, 'projects/earthengine-legacy/assets/projects/usgs-ssebop/tcorr_scene/daymet_median_v2_default']
]
for tcorr_index, coll_id in coll_id_list:
    image_coll = ee.ImageCollection(coll_id)\
        .filterMetadata('tcorr_index', 'not_equals', tcorr_index)
    #     .filter(ee.Filter.notNull(['tcorr_index']).Not())
    image_id_list = image_coll.aggregate_array('system:index').getInfo()
    print('  {}'.format(len(image_id_list)))

    for i, image_id in enumerate(sorted(image_id_list, reverse=True)):
        # print(f'{coll_id}/{image_id}')
        if i % 100 == 0:
            print(i, image_id)

        ee.data.updateAsset(
            asset_id=f'{image_coll_id}/{image_id}',
            asset={'properties': {'tcorr_index': tcorr_index}},
            update_mask=['properties.tcorr_index'])