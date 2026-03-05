import geopandas as gpd
import pandas as pd
import shapely
import numpy as np
import contextlib
import glob
import os
import shutil
import apsimxpy
from apsimxpy.field.soil.ssurgo import sdapoly, sdaprop
from apsimxpy.field.soil.ssurgo import soil_extraction as se
from apsimxpy.field.soil.ssurgo import saxton as sax
from apsimxpy.field.soil.ssurgo import soil_apsim as sa
from concurrent.futures import ProcessPoolExecutor, as_completed

# Mapping Region
region3_map = {
    # NW
    "Jasper County": "NC", "Lake County": "NC", "Laporte County": "NC", "Newton County": "NC", "Porter County": "NC", "Pulaski County": "NC", "Starke County": "NC", "White County": "NC",
    # NC
    "Kosciusko County":"NC","Wabash County":"NC","St Joseph County":"NC","Cass County": "NC", "Fulton County": "NC", "Howard County": "C", "Miami County": "NC", "Tippecanoe County": "NC", "Tipton County": "C", "Carroll County": "NC", "Clinton County": "C","Marshall County":"NC","Elkhart County":"NC",
    # NE
    "Adams County": "NE", "Allen County": "NE", "Dekalb County": "NE", "Huntington County": "NE", "Lagrange County": "NE", "Noble County": "NE", "Steuben County": "NE", "Wells County": "NE", "Whitley County": "NE",
    # WC
    "Benton County": "NC", "Fountain County": "NC", "Montgomery County": "NC", "Parke County": "NC", "Putnam County": "NC", "Vermillion County": "NC", "Warren County": "NC","Vigo County": "NC","Clay County": "NC",
    # C
    "Boone County": "C", "Hamilton County": "C", "Hancock County": "C", "Hendricks County": "C", "Johnson County": "C", "Madison County": "C", "Marion County": "C", "Morgan County": "C", "Shelby County": "C",
    # EC
    "Blackford County": "NE","Union County": "NE","Fayette County": "NE", "Delaware County": "NE", "Grant County": "C", "Henry County": "NE", "Jay County": "NE", "Randolph County":"NE","Rush County":"C","Wayne County":"NE",
    
    "Daviess County": "NC", "Sullivan County": "NC","Gibson County": "NC", "Knox County": "NC", "Perry County": "NC", "Pike County": "NC", "Posey County": "NC", "Spencer County": "NC", "Vanderburgh County": "NC", "Warrick County": "NC",
    # SC
    "Brown County": "NC", "Crawford County": "NC", "Dubois County": "NC", "Greene County": "NC", "Lawrence County": "NC", "Martin County": "NC", "Monroe County": "NC", "Orange County": "NC", "Owen County": "NC", "Washington County": "NC",
    # SE
    "Bartholomew County": "C", "Clark County": "NC", "Decatur County": "C", "Dearborn County": "NC", "Floyd County": "NC", "Franklin County": "NC", "Harrison County": "NC", "Jackson County": "NC", "Jefferson County": "NC", "Jennings County": "NC", "Ohio County": "NC", "Ripley County": "NC", "Scott County": "NC", "Switzerland County": "NC"
}
soil_path="/depot/ciampitti/data/WorkflowApsimNitrogenData/_4RunSimulationsData/soil"
weather_path="/depot/ciampitti/data/WorkflowApsimNitrogenData/_4RunSimulationsData/weather"

if os.path.exists(soil_path) and os.path.isdir(soil_path):
    shutil.rmtree(soil_path)
    print(f"Folder soil deleted")
os.makedirs(soil_path)
print(f"Folder soil created")

if os.path.exists(weather_path) and os.path.isdir(weather_path):
    shutil.rmtree(weather_path)
    print(f"Folder weather deleted")
os.makedirs(weather_path)
print(f"Folder weather created")

# Importing fields and counties
counties = gpd.read_file("/depot/ciampitti/data/WorkflowApsimNitrogenData/_AdditionalData/counties.geojson")
counties = counties[['name','geometry']]
counties.columns=['countyname','geometry']

# Importing fields
fields=gpd.read_file("/depot/ciampitti/data/WorkflowApsimNitrogenData/_2GridSamplingData/field_final_sample.geojson")
fields=fields[['id_cell','id_within_cell','geometry']]

counties["region"] = counties["countyname"].map(region3_map).fillna("Other/SandNI")
counties=counties[["region","countyname","geometry"]]

fields = fields.to_crs(counties.crs)

region_fields = gpd.sjoin(fields, counties, how='inner', predicate='intersects')

region_fields_sample = (
    region_fields.groupby('region', group_keys=False) 
       .apply(lambda x: x.sample(n=20, random_state=42)) 
)
# region_fields_sample=region_fields_sample[region_fields_sample['id_cell']==718]
region_fields_sample.reset_index(drop=True, inplace=True)

region_fields_sample.sort_values(by='id_cell',axis=0,inplace=True)

#  Getting atitude and longitude 

region_fields_sample = region_fields_sample.to_crs(epsg=32616)

accurate_centroids = region_fields_sample.centroid
centroids_geographic = accurate_centroids.to_crs(epsg=4326)

region_fields_sample['long'] = round(centroids_geographic.x, 7)
region_fields_sample['lat'] = round(centroids_geographic.y, 7)

# Reading plant dates
plantdate = gpd.read_file("/depot/ciampitti/data/WorkflowApsimNitrogenData/_AdditionalData/maize_countyStats_doyPercentPlanted_2000-2020_DeinesEtAl_vRSE.csv")
plantdate_ind=plantdate[plantdate['state']=='IN'][['county','Year','doy_10','doy_90']]

# Selcting starting and ending planting dates
plantdate_ind['doy_10']=pd.to_numeric(plantdate_ind['doy_10'])
plantdate_ind['doy_90']=pd.to_numeric(plantdate_ind['doy_90'])
plantdate_ind['Year']=pd.to_numeric(plantdate_ind['Year'])

# Grouping date by county
avg_planting = plantdate_ind.groupby('county')[['doy_10','doy_90','Year']].mean().reset_index()

avg_planting.rename(columns={'doy_10': 'avg_doy_10','doy_90': 'avg_doy_90','Year':'year'}, inplace=True)
avg_planting['avg_doy_10']=avg_planting['avg_doy_10'].astype('int')
avg_planting['avg_doy_90']=avg_planting['avg_doy_90'].astype('int')
avg_planting['tillage_date'] = avg_planting['avg_doy_10'] - 8
avg_planting['avg_year']=avg_planting['year'].astype('int')

# Changing date format (%Y-%j)
avg_planting['startdate']= pd.to_datetime(avg_planting['avg_year'].astype(str) + '-' + 
                       avg_planting['avg_doy_10'].astype(str), format='%Y-%j')
avg_planting['enddate']= pd.to_datetime(avg_planting['avg_year'].astype(str) + '-' + 
                       avg_planting['avg_doy_90'].astype(str), format='%Y-%j')
avg_planting['tillage_date']= pd.to_datetime(avg_planting['avg_year'].astype(str) + '-' + 
                       avg_planting['tillage_date'].astype(str), format='%Y-%j')

start_dates=avg_planting['startdate']
end_dates=avg_planting['enddate']
tillage_date=avg_planting['tillage_date']

# Apsim planting dates format
formatted_start_date = start_dates.dt.strftime("%d-%b").str.lower()
formatted_end_date =  end_dates.dt.strftime("%d-%b").str.lower()
formatted_tillage_date =  tillage_date.dt.strftime("%d-%b").str.lower()

avg_planting['apsim_start_date'] = formatted_start_date 
avg_planting['apsim_end_date'] = formatted_end_date
avg_planting['apsim_tillage_date'] = formatted_tillage_date

# Changing names of some counties
avg_planting['county'].replace({'St. Joseph County':'St Joseph County',
                                'DeKalb County':'Dekalb County',
                                'LaGrange County':'Lagrange County',
                                'LaPorte County':'Laporte County'},inplace=True)

region_fields_sample=pd.merge(region_fields_sample,avg_planting[['county','apsim_start_date','apsim_end_date','apsim_tillage_date','avg_doy_10','avg_doy_90','avg_year']],left_on='countyname',right_on='county',how='left').drop(columns=['index_right','county'])

region_fields_sample.to_file("/depot/ciampitti/data/WorkflowApsimNitrogenData/_3AgroDataExtractionData/calibration_sample.geojson", driver="GeoJSON")
# The apsimxpy module allows you to extract weather and soil properties
init_obg=apsimxpy.Initialize(apsim_folder_input='/home/jjolaher/WorkflowApsimNitrogenRCAC/WorkflowApsimNitrogenIndiana/ApsimxpyGautschi',apsim_file_input='CornSoybean_C')


# Set dates to extract weather variables
clock1=apsimxpy.Clock(init_obj=init_obg)
clock1.set_StartDate((1,1,1980)) 
clock1.set_EndDate((31,12,2024))

met=apsimxpy.Weather(init_obg)
soils=pd.DataFrame()
def process_field(row):
    # Extraction of soil variables
    ssurgo_soil=se.get_poly_soil(row,plot=True)
    main_soil=se.get_main_soil(ssurgo_soil,plot=True)
    
    row_soil = ssurgo_soil[ssurgo_soil['mukey'] == main_soil]
    muname = row_soil['muname'].iloc[0].lower()
    
    if muname.startswith(("borrow", "urban", "water")):
        return f"⚠ No valid Area: {row_soil['muname'].iloc[0]}", None

    props=se.get_soil_props(ssurgo_soil,main_soil)
    s_apsim=sa.soil_apsim(props)
    s_apsim['id_cell']=row['id_cell']
    s_apsim['id_within_cell']=row['id_within_cell']
    # Extraction of weather variables
    lat = row['lat']
    long = row['long']
    filename = f"w_id_{row['id_cell']}_{row['id_within_cell']}"
    met.get_weather((round(long,7), round(lat,7)), clock1, filename)
    print(f"Weather and Soil Variables extracted for field {row['id_cell']}-{row['id_within_cell']}")
    return s_apsim

soils_list = []

with ProcessPoolExecutor(max_workers=10) as executor:

    futures = {executor.submit(process_field, row): idx for idx, row in region_fields_sample.iterrows()}

    for future in as_completed(futures):
        s_apsim = future.result()
        if s_apsim is not None:
            soils_list.append(s_apsim)

soils = pd.concat(soils_list, ignore_index=True)

# Custom soil profiles
new_layers = [
    (0,50),(50,100),
    (100,150),(150,200),(200,400),
    (400,600),(600,800),(800,1000),
    (1000,1500),(1500,2000)
]

weighted_vars = [
    'SAND','CLAY','SILT','BD','KSAT','SAT','DUL','LL','AirDry',
    'PO','SWCON','CONA','DiffusConst','XF_maize','KL_maize',
    'e','PH','CO','CEC','SW'
]

copy_vars = ['RootCN','RootWt','id_cell','id_within_cell']

def weighted_layer(df, ztop, zbot):
    out = {}
    for var in weighted_vars:
        num, den = 0.0, 0.0
        for _, r in df.iterrows():
            overlap = max(0, min(zbot, r.BOT_LAYER) - max(ztop, r.TOP_LAYER))
            if overlap > 0:
                num += overlap * r[var]
                den += overlap
        out[var] = num / den if den > 0 else None
    return out

rows = []

for id_cell, df_cell in soils.groupby(['id_cell', 'id_within_cell']):

    df_cell = df_cell.sort_values('TOP_LAYER')

    for ztop, zbot in new_layers:
        row = weighted_layer(df_cell, ztop, zbot)

        row['TOP_LAYER'] = ztop
        row['BOT_LAYER'] = zbot
        row['THICK'] = zbot - ztop

        for v in copy_vars:
            row[v] = df_cell[v].iloc[0]

        rows.append(row)

new_profile = pd.DataFrame(rows)

new_profile.to_csv("/depot/ciampitti/data/WorkflowApsimNitrogenData/_4RunSimulationsData/soil/soils.csv",index=False)

print('Variables extracted successful!!! step 3/4')
