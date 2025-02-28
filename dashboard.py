from fastapi import APIRouter
from fastapi import Depends
from storage.database_async import get_db_async
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from cache import cache_set
from authentication.authorization import get_token_async
from storage.database_vdm_async import get_vdm_db_async
from storage import querydata
from common.functions import read_file_async
from datetime import datetime,date
from routers.cii import rating
from sklearn.linear_model import LinearRegression
from cache import utility
from common.configuration import CACHEKEY
from fastapi.encoders import jsonable_encoder
from dateutil.relativedelta import relativedelta
import json
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.linear_model import LinearRegression
import statistics
import time
from sklearn.linear_model import LinearRegression
import threading
from statsmodels.tsa.arima.model import ARIMA

CACHEKEY = CACHEKEY()

router = APIRouter(
   prefix="",
   tags=["Dashboard"],
   )



@router.get('/api/v1/all_sfoc_trend/{fleet}')
async def  get_sfoc_trend(fleet:str = None,db : AsyncSession = Depends(get_db_async),vdm_db : AsyncSession = Depends(get_vdm_db_async),token : AsyncSession = Depends(get_token_async)):
    # start = time.time()
    # username = token['username']
    # user_vessels = await cache_set.get_user_vessel(db,username)
    # # return user_vessels
    # if user_vessels:
    #     user_vessels = list((user_vessels[0]['imo']).split(","))
    # f = open('stub/sfoc_trend.json')
    # sfoc_datas = json.load(f)
    mcr_data = await cache_set.get_all_vdm_vessel_attribute(vdm_db)
    
    if fleet == 'All':
        mcr_data = list(filter(lambda x:x['attribute_id'] == 7 , mcr_data))
        # mcr_data = await cache_set.get_mcr_filter(vdm_db)
        pass
    else:
        # mcr_data = await cache_set.get_mcr_filter_for_all(vdm_db ,fleet)
        mcr_data = list(filter(lambda x:x['fleet'] == int(fleet) and x['attribute_id'] == 7 , mcr_data))

    vessel_list_fleet= [i['imo'] for i in mcr_data]
    vessel_list_fleet = set(vessel_list_fleet)
    vessel_list = list(vessel_list_fleet)
    
    
    all_me_data = await cache_set.get_all_me_datas(db,vessel_list,fleet)
    
    
    
    if not all_me_data:
        return {'data':[],'error':"no data in engine data"}
    
    dfs = pd.DataFrame(all_me_data)
    dfs['engine_load'] = dfs['engine_load'].str.extract(r'(\d+\.\d+)').astype(float)
    dfs = dfs.fillna(0)
   
    dfs['engine_load'] = pd.to_numeric(dfs['engine_load'])
    dfs=dfs.to_json(orient="records")#convert dataframe to json 
    all_engine_datas=json.loads(dfs)
    
    #all_engine_datas = list(filter(lambda x:x['sfoc'] >= 50 and float(x['engine_load']) >=50 ,engine_data))
    
    
    sfoc_trend_list = []
   
      
    shop = await cache_set.get_all_shop_datas_for_dashboard(db, vessel_list,fleet)
    
    if not shop:
        return {'data':[],'error':"no data in shop trial data"}
    async def linear_regression(shop):
        load_a = [float(ele['load']) for ele in shop if ele['load'] is not None] #remove null values from list
        # sfoc_y = [float(sle['sfoc']) for sle in shop if sle['sfoc'] is not None]
        sfoc_y=[float(sle['sfoc']) for sle in shop if sle['sfoc'] not in [None, 'None', '']]

        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        #       linear model and polynomial    
        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        #  "entering linearmodule")
        squared_load_a = [float(number) ** 2 for number in load_a]
        load_x = np.column_stack((load_a, squared_load_a))    
        if len(sfoc_y) >= len(load_x):
                lenth = len(load_x)
                sfoc_y = sfoc_y[0:lenth]  
        else:
            lenth = len(sfoc_y)
            load_x = load_x[0:lenth]
        
        if  len(load_x) != 0 or len(sfoc_y) != 0:
            model = LinearRegression().fit(load_x,sfoc_y)
                
            interc = model.intercept_ 
            slope = model.coef_
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            k = float(interc)    #coefficients[1]
            n2 = float(slope[0]) #coefficients[2]
            n1 = float(slope[1]) #coefficients[3]
        else:
            k = None
            n2 = None
            n1 = None
        print("exit")    
        return k,n2,n1
    
    
    sfoc_trend_list = [] 
    # vessel = ['8509375']
    vessel = ['9710426']
    
    for i in vessel_list:
        dicti = {}
        
        shop_trial_single = list(filter(lambda x:x['imo'] == str(i) ,shop))
        k,n2,n1 = await linear_regression(shop_trial_single)
        
        print("spread")    
        
        if k is not None and  n2 is not None and  n1 is not None:
            yob = list(filter(lambda x:x['imo'] == i and x['attribute_id'] == 7 , mcr_data))

            try:    
                yob = yob[0]['value']
            except:
                continue   
            
            if not yob or yob == '':
                continue 
            
            sfoc_data = list(filter(lambda x:x['imo'] == str(i) ,all_engine_datas))
            sfoc_data = sorted(sfoc_data, key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'), reverse=True)
            
            if not sfoc_data:
                continue 
            row = 0
            con = 0
            while True:
                try:
                    if sfoc_data[row]['date']!= 0:
                        dicti['date'] = datetime.strptime(sfoc_data[row]['date'] , '%Y-%m-%d')
                        break
                    else:
                        row = row + 1
                        dicti['date'] = datetime.strptime(sfoc_data[row]['date'] , '%Y-%m-%d')
                except Exception as e:
                    row = 0
                    con = 1
                    break
            if con == 1:
                continue    
            
        
            try:
                yob = datetime.strptime(yob , '%m/%d/%Y').strftime('%Y')
            except:
                yob = yob
            dicti['yob'] = yob
            dicti['imo'] = i
            
            
            try:         
                dicti['sfoc'] = round(float(sfoc_data[row]['sfoc']),2)  
            except:
                dicti['sfoc'] = "no sfoc"  
            
            
            print("resultresultresult",sfoc_data[row])
            
            while True:
                try:
                    testy = round(n1*float(sfoc_data[row]['engine_load'])*float(sfoc_data[row]['engine_load']) + n2*float(sfoc_data[row]['engine_load']) + k)
                    deviation = ((sfoc_data[row]["sfoc"]-testy)/ testy)*100
                    dicti['engine_load'] = sfoc_data[row]['engine_load']
                    dicti['sfoc_shop'] = float(testy)
                    dicti['deviation'] = round(deviation,2)
                    if deviation >= 5:
                        dicti['type'] = "Upper High Deviation"
                    elif deviation <= -5:
                        dicti['type'] = "Lower High Deviation"
                    else:
                        dicti['type'] = "Normal"
                    break   
                except IndexError:
                    print("break")
                    break
            dicti['vessel_name'] = list(filter(lambda x:x['imo'] == i , mcr_data))[0]['name']
            dicti['month'] = dicti['date'].strftime('%b')
            dicti['date'] =  dicti['date'].strftime('%d %b %Y')
            dicti['id_vessel'] = sfoc_data[0]['id_vessel']
            dicti['vessel_age'] = int(datetime.strptime(dicti['date'] , '%d %b %Y').strftime('%Y')) - int(yob)
            print("dictidicti",dicti)     
            if dicti['deviation']>= -20 and dicti['deviation']<= 20:
                sfoc_trend_list.append(dicti)
    print("ther end")
    return {"data":sfoc_trend_list}


    
# @router.get('/api/v1/cargo')
# def index(db: AsyncSession = Depends(get_db_async),vdm_db: AsyncSession = Depends(get_vdm_db_async)):
#     print("stating.....")
#     data = await utility.get_data_async(key=CACHEKEY.FINAL_RESULT_DASHBOAR_CARGO)
#     cache = False
#     if data is not None:

#         cache = True
#         print("from cache")
#     else:
    
#         vessel = await cache_set.get_vdm_vessels(vdm_db)
#         vessel_list = [i['imo'] for i in vessel]
#         mcr_data = await cache_set.get_mcr_filter(vdm_db )
        
#         data_dict = {item['imo']: {'dwt': '', 'ship_type': '', 'ship_name': ''} for item in mcr_data}
        
#         for item in mcr_data:
            
#             data_dict[item['imo']][{8: 'dwt', 4: 'ship_type', 61: 'ship_name'}.get(item['attribute_id'])] = item['value']
            

        
#         data2 = []
#         # print(mcr_data)
#         for i , j in data_dict.items():
#             # print("i:",i,"j:",j)
#             vessel_data_dict = {}
#             vessel_data_dict['imo'] = i
#             vessel_data_dict['fleet'] = list(filter(lambda x : x['imo'] == i , mcr_data))[0]['fleet_id']
#             vessel_data_dict['dwt'] = j['dwt']
#             if j['ship_type'] == '1':
#                 vessel_data_dict['type'] = 'Container'
#             elif j['ship_type'] == '2':
#                 vessel_data_dict['type'] = 'Bulk Carrier'
#             elif j['ship_type'] == '5':
#                 vessel_data_dict['type'] = 'ROPAX' 
#             elif j['ship_type'] == '4':
#                 vessel_data_dict['type'] = 'PAX' 
#             elif j['ship_type'] == '3':
#                 vessel_data_dict['type'] = 'PCTC'
#             elif j['ship_type'] == '6':
#                 vessel_data_dict['type'] = 'TUG'                    
#             vessel_data_dict['name'] = j['ship_name']
        
            
#             data2.append(vessel_data_dict)

#         year = str((date.today()).year)
#         data = await cache_set.get_cargo_data(db, year,vessel_list , fleet=None)
        
#         def Cargo_Utilization(data):
#             print("inside function")
#             #-----------chat gpt code -------------------------------------
#             df=pd.DataFrame.from_dict(data)
        
#             df_data=pd.DataFrame.from_dict(data2)
#             df = df.merge(df_data, on='imo', how='left')
#             #------------end chat gpt code -------------------------------
            
#             # df=pd.DataFrame.from_dict(data)
#             # df_dwt=pd.DataFrame.from_dict(dwt)
#             # df_ship_type=pd.DataFrame.from_dict(ship_type)
#             # df_name=pd.DataFrame.from_dict(name)
            
#             # imo_dwt = dict(zip(df_dwt['imo'], df_dwt['value']))
#             # df['dwt'] = df['imo'].map(imo_dwt)
            
#             # imo_ship_type = dict(zip(df_ship_type['imo'], df_ship_type['value']))
#             # df['ship_type'] = df['imo'].map(imo_ship_type)
#             # print("df",df["report_date_time"])
            
#             # imo_name = dict(zip(df_ship_type['imo'], df_name['value']))
#             # df['name'] = df['imo'].map(imo_name)
            
#             df['datetime'] = pd.to_datetime(df['report_date_time'],format='%Y-%m-%dT%H:%M:%S%z')
#             df['Month_name'] = df['datetime'].dt.strftime('%B')
#             df['Month'] = df['datetime'].dt.strftime('%b')
#             df['Year'] = df['datetime'].dt.strftime('%Y')
#             df['Date'] = df['datetime'].dt.strftime('%d')
            
#             #Total HS,LS,MGO and Total Fuel
#             convert_dict = {
#                     'fuel_me_rsdl_hs': float,
#                     'fuel_aux_rsdl_hs': float,
#                     'fuel_boiler_rsdl_hs': float,
                    
#                     'fuel_me_rsdl_vls': float,
#                     'fuel_me_rsdl_uls': float,
#                     'fuel_aux_rsdl_vls': float,
#                     'fuel_aux_rsdl_uls':float,
#                     'fuel_boiler_rsdl_vls':float,
#                     'fuel_boiler_rsdl_uls':float,
                    
#                     'fuel_me_dstlt_vls':float,
#                     'fuel_me_dstlt_uls':float,
#                     'fuel_me_tnktnr_dstlt_vls':float,
#                     'fuel_aux_dstlt_vls':float,
#                     'fuel_aux_dstlt_uls':float,
#                     'fuel_aux_tnktnr_dstlt_vls':float,
#                     'fuel_boiler_dstlt_vls':float,
#                     'fuel_boiler_dstlt_uls':float,
#                     'fuel_boiler_tnktnr_dstlt_vls':float,
                    
                    
                    
#                     }
#             df = df.astype(convert_dict)
#             df['Total_Calculated_HS']= df[['fuel_me_rsdl_hs',"fuel_aux_rsdl_hs",'fuel_boiler_rsdl_hs']].sum(axis=1)
#             df['Total_Calculated_LS'] = df[['fuel_me_rsdl_vls','fuel_me_rsdl_uls','fuel_aux_rsdl_vls','fuel_aux_rsdl_uls', 'fuel_boiler_rsdl_vls','fuel_boiler_rsdl_uls']].sum(axis=1)
#             df['Total_Calculated_ULS'] = df[['fuel_me_dstlt_vls','fuel_me_dstlt_uls','fuel_me_tnktnr_dstlt_vls','fuel_aux_dstlt_vls','fuel_aux_dstlt_uls','fuel_aux_tnktnr_dstlt_vls','fuel_boiler_dstlt_vls','fuel_boiler_dstlt_uls','fuel_boiler_tnktnr_dstlt_vls']].sum(axis=1)
#             df['Total_Calculated_Fuel'] = df[['Total_Calculated_HS' ,'Total_Calculated_LS' , 'Total_Calculated_ULS']].sum(axis=1)
            
            
#             #HS_CO2,LSCO2,MGO_CO2 and Total CO2
#             df['HS_CO2'] = 3.114 * df["Total_Calculated_HS"]
#             df['LS_CO2'] = 3.151 * df["Total_Calculated_LS"]
#             df['ULS_CO2'] = 3.206 * df["Total_Calculated_ULS"]
#             df['Total_CO2'] = df[['HS_CO2' ,'LS_CO2' ,'ULS_CO2']].sum(axis=1)
#             df=df[["report_date_time",'datetime', 'imo','name', 'fleet','Month', 'Year', 
#                                                 'Month_name','voyage','Total_CO2',"miles_by_gps","cargo_total" , 'dwt' , 'type']]
            
            
            
#             df['voyage'] = df.groupby(['imo'])['voyage'].transform(lambda v: v.ffill())
#             df['voyage'] = df.groupby(['imo'])['voyage'].transform(lambda v: v.bfill())
#             df_sort_new=df.sort_values(by=["report_date_time"])
#             df_sort_1=df_sort_new[["imo","name","fleet","Month","Year","Month_name","type","voyage","dwt","cargo_total","miles_by_gps"]]#fleet
        
#             #Cargo Utilization
#             df_sort_1= df_sort_1.fillna(0)
#             df_sort_1 = df_sort_1.replace("", 0)
            
        
#             df_sort_1["dwt"]=df_sort_1["dwt"].astype(float)
#             df_sort_1["miles_by_gps"]=df_sort_1["miles_by_gps"].astype(float)
#             df_sort_1["cargo_total"]=df_sort_1["cargo_total"].astype(float)
            
#             df_cargo_utilize=df_sort_1.groupby(['imo',"name","type",'voyage','fleet']).agg({'dwt':'mean','miles_by_gps':'sum','cargo_total':'mean'}).reset_index()#fleet
#             df_cargo_utilize["Cargo_voyage"]=((df_cargo_utilize["cargo_total"]*df_cargo_utilize["miles_by_gps"])/(df_cargo_utilize["dwt"]))
#             df_cargo_utilize_1=df_cargo_utilize.groupby(['imo',"name","type","fleet"]).agg({'dwt':'mean','miles_by_gps':'sum','cargo_total':'sum','Cargo_voyage':'sum'}).reset_index()
#             df_cargo_utilize_1["Cargo_utilization"]=((df_cargo_utilize_1["Cargo_voyage"])/(df_cargo_utilize_1["miles_by_gps"]))
#             df_cargo_utilize_1["Cargo_utilization"] = df_cargo_utilize_1['Cargo_utilization'].fillna(0)
#             df_cargo_utilize_1["Cargo_utilization"] = df_cargo_utilize_1['Cargo_utilization'].replace("", 0)
#             df_cargo_utilize_1=df_cargo_utilize_1.round(decimals = 2)
#             df_cargo_utilize_1 = df_cargo_utilize_1.rename({"name": 'Vessel Name', "Cargo_utilization": 'Cargo Utilization'}, axis=1)
#             df_cargo_utilize_1["Cargo Utilization"]=(100 * df_cargo_utilize_1["Cargo Utilization"]).astype(float)
            
            
            
#             #rating
#             def Cargo_rating(y):
#                 if y>60:
#                     return "A"
#                 elif y>=50 and y<=60:
#                     return "B"
#                 elif y>=40 and y<=50:
#                     return "C"
#                 elif y>=30 and y<=40:
#                     return "D"
#                 else:
#                     return "E"
            
#             df_cargo_utilize_1['Rating'] = df_cargo_utilize_1.apply(lambda x: Cargo_rating(x['Cargo Utilization']), axis=1)
            
#             #rating Color
#             def Cargo_rating_color(y):
#                 if y=="A":
#                     return "green"
#                 elif y=="B":
#                     return "lightgreen"
#                 elif y=="C":
#                     return "yellow"
#                 elif y=="D":
#                     return "orange"
#                 elif y=="E":
#                     return "red"
            
#             df_cargo_utilize_1['color'] = df_cargo_utilize_1.apply(lambda x: Cargo_rating_color(x['Rating']), axis=1)
#             return df_cargo_utilize_1

#         df_cargo_utilize_1=Cargo_Utilization(data)
        
#         df_cargo_utilize_Container=df_cargo_utilize_1[df_cargo_utilize_1["type"]=="Container"]
#         df_cargo_utilize_Container=df_cargo_utilize_Container.sort_values(by="Cargo Utilization",ascending=False)
#         df_cargo_utilize_Container['rank'] = df_cargo_utilize_Container['Cargo Utilization'].rank(ascending=False,method='first')
#         df_cargo_utilize_Container['rank']=df_cargo_utilize_Container['rank'].astype(int)
#         df_cargo_utilize_Container=df_cargo_utilize_Container[["Vessel Name","dwt","Cargo Utilization","Rating","color","rank"]]
#         cargo_container = df_cargo_utilize_Container.to_json(orient="records")
#         cargo_container = json.loads(cargo_container)
        

#         df_cargo_utilize_Bulker=df_cargo_utilize_1[df_cargo_utilize_1["type"]=="Bulk Carrier"]
#         df_cargo_utilize_Bulker=df_cargo_utilize_Bulker.sort_values(by="Cargo Utilization",ascending=False)
#         df_cargo_utilize_Bulker['rank'] = df_cargo_utilize_Bulker['Cargo Utilization'].rank(ascending=False,method='first')
#         df_cargo_utilize_Bulker['rank']=df_cargo_utilize_Bulker['rank'].astype(int)
#         df_cargo_utilize_Bulker=df_cargo_utilize_Bulker[["Vessel Name","dwt","Cargo Utilization","Rating","color","rank"]]
#         cargo_bulker = df_cargo_utilize_Bulker.to_json(orient="records")
#         cargo_bulker = json.loads(cargo_bulker)
        
        
        
#         df_cargo_utilize_PCTC=df_cargo_utilize_1[df_cargo_utilize_1["type"]=="PCTC"]
#         df_cargo_utilize_PCTC=df_cargo_utilize_PCTC.sort_values(by="Cargo Utilization",ascending=False)
#         df_cargo_utilize_PCTC['rank'] = df_cargo_utilize_PCTC['Cargo Utilization'].rank(ascending=False,method='first')
#         df_cargo_utilize_PCTC['rank']=df_cargo_utilize_PCTC['rank'].astype(int)
#         df_cargo_utilize_PCTC=df_cargo_utilize_PCTC[["Vessel Name","dwt","Cargo Utilization","Rating","color","rank"]]
#         cargo_pctc = df_cargo_utilize_PCTC.to_json(orient="records")
#         cargo_pctc = json.loads(cargo_pctc)    
        
        
#         df_cargo_utilize_Ropax=df_cargo_utilize_1[df_cargo_utilize_1["type"]=="ROPAX"]
#         df_cargo_utilize_Ropax=df_cargo_utilize_Ropax.sort_values(by="Cargo Utilization",ascending=False)
#         df_cargo_utilize_Ropax['rank'] = df_cargo_utilize_Ropax['Cargo Utilization'].rank(ascending=False,method='first')
#         df_cargo_utilize_Ropax['rank']=df_cargo_utilize_Ropax['rank'].astype(int)
#         df_cargo_utilize_Ropax=df_cargo_utilize_Ropax[["Vessel Name","dwt","Cargo Utilization","Rating","color","rank","fleet"]]
#         cargo_ropax = df_cargo_utilize_Ropax.to_json(orient="records")
#         cargo_ropax = json.loads(cargo_ropax)
        
#         data = {
#     'cargo_container':cargo_container,
#     'cargo_bulker':cargo_bulker,
#     'cargo_pctc':cargo_pctc,
#     'cargo_ropax':cargo_ropax}
       
    
#         try:
#                 if data is not None:
#                     cache = False
#                     data = json.dumps(data)
#                     state = await utility.set_data_async(key=CACHEKEY.FINAL_RESULT_DASHBOAR_CARGO, value= data, seconds = 604800)
                    
                
#                     if state is True:
#                             print('Cache Set Successfully') 

#         except:
#                 print('cache set failure')

#     data = json.loads(data)

#     return {'data':data}

    
     
        
@router.get('/api/v1/steamming')
async def index(db: AsyncSession = Depends(get_db_async),vdm_db: AsyncSession = Depends(get_vdm_db_async),token : AsyncSession = Depends(get_token_async)):
    # user_vessels = await cache_set.get_user_vessel(db,token['username'])
    
    data = await utility.get_data_async(key=CACHEKEY.FINAL_RESULT_DASHBOAR_STEAMMING)
    cache = False
    if data is not None:

        cache = True
        print('from cache')
    else:

        print("stating.....")
        
        attributes_id = [4,8,61]
        # vessel = await cache_set.get_vdm_vessels(vdm_db)
        vessel = await cache_set.get_all_vdm_vessel_attribute(vdm_db)
        vessel = list(filter(lambda x:x['attribute_id'] in attributes_id , vessel))
        
        
        vessel_list = []
        for i in vessel:
            if i['imo'] not in vessel_list:
                vessel_list.append(i['imo'])

        year = str((date.today()).year)
        # year = "2022"
        mcr_data = vessel
        data_dict = {item['imo']: {'dwt': '', 'ship_type': '', 'ship_name': ''} for item in mcr_data}
        
        for item in mcr_data:
            
            data_dict[item['imo']][{8: 'dwt', 4: 'ship_type', 61: 'ship_name'}.get(item['attribute_id'])] = item['value']
            

        
        data2 = []
        # print(mcr_data)
        for i , j in data_dict.items():
            # print("i:",i,"j:",j)
            vessel_data_dict = {}
            vessel_data_dict['imo'] = i
            vessel_data_dict['fleet'] = list(filter(lambda x : x['imo'] == i , mcr_data))[0]['fleet_name']
            vessel_data_dict['dwt'] = j['dwt']
            if j['ship_type'] == '1':
                vessel_data_dict['type'] = 'Container'
            elif j['ship_type'] == '2':
                vessel_data_dict['type'] = 'Bulk Carrier'
            elif j['ship_type'] == '5':
                vessel_data_dict['type'] = 'ROPAX' 
            elif j['ship_type'] == '4':
                vessel_data_dict['type'] = 'PAX' 
            elif j['ship_type'] == '3':
                vessel_data_dict['type'] = 'PCTC'
            elif j['ship_type'] == '6':
                vessel_data_dict['type'] = 'TUG'                    
            vessel_data_dict['name'] = j['ship_name']
        
            
            data2.append(vessel_data_dict)
        if vessel_list:
            data = await cache_set.get_steaming_data_by_user(db, year ,vessel_list,"")   
        else:
            return {'data': []}

        async def Steaming_percentage(data):
            df=pd.DataFrame.from_dict(data)
            df_data=pd.DataFrame.from_dict(data2)
            df = df.merge(df_data, on='imo', how='left')
            df['Date'] = pd.to_datetime(df['report_date_time']).apply(lambda x:x.strftime("%d"))
            df['Month'] = pd.to_datetime(df['report_date_time']).apply(lambda x:x.strftime("%m"))
            df['Year'] = pd.to_datetime(df['report_date_time']).apply(lambda x:x.strftime("%Y"))
            df['Month_name'] = pd.to_datetime(df['report_date_time']).apply(lambda x:x.strftime("%B"))
            df['date'] = pd.to_datetime(df["report_date_time"]).dt.date
            
            df_sort=df.sort_values(by=["report_date_time"])
            df_sort= df_sort.fillna(0)
            df_sort = df_sort.replace("", 0)
            
            
            
            df_sort["me_fuel_only_steaming_time"]=df_sort["me_fuel_only_steaming_time"].astype(float)
            
            df_1 = df_sort.groupby(['imo','name','fleet','type','Year','Month',"Month_name"])['Date'].nunique().reset_index()
            df_2 = df_1.groupby(['imo','name','fleet','type','Year'])['Date'].sum().reset_index()
            df_2 = df_2.rename({"Date":"Total_Date"},axis=1)
            df_time = df_sort.groupby(['imo','name',"type",'Year','fleet'])['me_fuel_only_steaming_time'].sum().reset_index()
            df_time = df_time.rename({"me_fuel_only_steaming_time":"Total_ME_Steaming_Time"},axis=1)
            df_time["Total_ME_Steaming_Time"] = (df_time["Total_ME_Steaming_Time"]/24).round(0).astype(int)
        
            dict_total_days= pd.Series(df_2['Total_Date'].values,index=df_2['imo']).to_dict()
            df_time['Total_Date'] = np.nan
            df_time['Total_Date'] = df_time['Total_Date'].fillna(df_time['imo'].apply(lambda x: dict_total_days.get(x)))
            df_time['Total_Date']=df_time['Total_Date'].astype(int)
            df_time["Steaming_time"]=((df_time["Total_ME_Steaming_Time"]/df_time['Total_Date'])*100).round(2)
            return df_time


        df_time=await Steaming_percentage(data)
        print("50% complete")
        
        
        df_time_Container=df_time[df_time["type"]=="Container"]
        df_time_Container=df_time_Container.sort_values(by="Steaming_time")
        df_time_Container["Steaming_time_mean"]=df_time_Container["Steaming_time"].mean()
        df_time_Container=df_time_Container[["name","Steaming_time","Steaming_time_mean","fleet"]].round(1)
        df_time_Container = df_time_Container.to_json(orient = 'records')
        df_time_container = json.loads(df_time_Container)

        df_time_Bulker=df_time[df_time["type"]=="Bulk Carrier"]
        df_time_Bulker=df_time_Bulker.sort_values(by="Steaming_time")
        df_time_Bulker["Steaming_time_mean"]=df_time_Bulker["Steaming_time"].mean()
        df_time_Bulker=df_time_Bulker[["name","Steaming_time","Steaming_time_mean","fleet"]].round(1)
        df_time_Bulker = df_time_Bulker.to_json(orient = 'records')
        df_time_bulker = json.loads(df_time_Bulker)



        # df_time_pctc=df_time[df_time["ship_type"]=="3"]
        # df_time_pctc=df_time_pctc.sort_values(by="Steaming_time")
        # df_time_pctc["Steaming_time_mean"]=df_time_pctc["Steaming_time"].mean()
        # df_time_pctc=df_time_pctc[["name","Steaming_time","Steaming_time_mean"]].round(1)
        # df_time_pctc = df_time_pctc.to_json(orient = 'records')
        # df_time_pctc = json.loads(df_time_pctc)



        
        # df_time_Ropax=df_time[df_time["ship_type"]=="5"]
        # df_time_Ropax=df_time_Ropax.sort_values(by="Steaming_time")
        # df_time_Ropax["Steaming_time_mean"]=df_time_Ropax["Steaming_time"].mean()
        # df_time_Ropax=df_time_Ropax[["name","Steaming_time","Steaming_time_mean"]].round(1)
        # df_time_Ropax = df_time_Ropax.to_json(orient = 'records')
        # df_time_Ropax = json.loads(df_time_Ropax)
        # print("ending")
        data = {'df_time_container':df_time_container,
        'df_time_bulker':df_time_bulker}

        try:
                if data is not None:
                    cache = False
                    data = json.dumps(data)
                    state = await utility.set_data_async(key=CACHEKEY.FINAL_RESULT_DASHBOAR_STEAMMING, value= data , seconds =604800)
                    
                
                    if state is True:
                            print('Cache Set Successfully') 

        except:
                print('cache set failure')

    data = json.loads(data)

    return {'data':data}

@router.get('/api/v1/noondataall')
async def index(db: AsyncSession = Depends(get_db_async),token : AsyncSession = Depends(get_token_async)):
    print("Getting All Noondata")
    data =  await querydata.get_noona_data_all(db)
    print("Completed")
    return data


    
    
    
@router.get('/api/v1/hullmonitoring/{fleet}')
async def index(fleet:str = None,db : AsyncSession = Depends(get_db_async),vdm_db:AsyncSession = Depends(get_vdm_db_async),token : AsyncSession = Depends(get_token_async)):
    print("stating hull performance api")
    result = await utility.get_data_async(key=CACHEKEY.HULLMONITORING_DASHBOARD_RESULT+str(fleet))
    cache = False
    if result is not None:
        cache = True
    else:
        today = datetime.today()
        attributes_id = [20,148]
        mcr_data = await cache_set.get_all_vdm_vessel_attribute(vdm_db)
        if fleet == 'All':
            # mcr_data = await cache_set.get_mcr_filter(vdm_db)
            mcr_data = list(filter(lambda x:x['attribute_id'] in attributes_id, mcr_data))
            
            # pass
        else:
            # mcr_data = await cache_set.get_mcr_filter_for_all(vdm_db ,fleet)
            mcr_data = list(filter(lambda x:x['fleet'] == int(fleet) and x['attribute_id'] in attributes_id, mcr_data))
            
        vessel_list_fleet= [i['imo'] for i in mcr_data]
        vessel_list_fleet = set(vessel_list_fleet)
        imo_list = list(vessel_list_fleet)

        shoptrial_data = await cache_set.get_shoptrialdata(db)
        # allvessel_data = await cache_set.get_all_vessel_by_imo_list(vdm_db,fleet,imo_list)
        # return shoptrial_data
        all_me_data = await cache_set.get_all_engine_datas(db,fleet,imo_list)
        if not all_me_data:
            return {"data":[]}
        
        keydate_data = await cache_set.get_all_keydates(db)
    
        speed_filter = await cache_set.get_speed_filter(db)
        
        keydate_data_time = datetime.now()

        latest_speed_date = datetime.now()

        today = datetime.now()

        year = today.year

        noon_data = []
        for i in range(2014, year+1):
            cache_status = True
            if i == year:
                cache_status = False

            noon_data_by_year = await cache_set.get_all_noondata_by_year(db,i,cache_status)
    
            if noon_data_by_year is not None:
                noon_data = noon_data + noon_data_by_year

        speed_loss = 'pi_stw'
        fuel = 'fo_nor_stw'
        speed = 'speed_by_log'

        avg_speed_data = []
        
        key_date_sort = keydate_data
        print("Starting")
        def data_handling(i,avg_speed_data):
            if i == '' or not i:
                return 0
            
            shoptrial_datas = list(filter(lambda x:x['imo'] == str(i) ,shoptrial_data))
    
            load_a = [float(ele['load']) for ele in shoptrial_datas if ele['load'] is not None] #remove null values from list
            sfoc_y = [float(sle['sfoc']) for sle in shoptrial_datas if sle['sfoc'] is not None]
            
            
            
            
            
            
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            #       linear model and polynomial    
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            squared_a = [float(number) ** 2 for number in load_a]
            load_x = np.column_stack((load_a, squared_a))
            if len(sfoc_y) >= len(load_x):
                lenth = len(load_x)
                sfoc_y = sfoc_y[0:lenth]  
            else:
                lenth = len(sfoc_y)
                load_x = load_x[0:lenth]
            
            if  len(load_x) != 0 or len(sfoc_y) != 0:
                model = LinearRegression().fit(load_x,sfoc_y)
                    
                interc = model.intercept_ 
                slope = model.coef_
                #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                k = float(interc)    #coefficients[1]
                n2 = float(slope[0]) #coefficients[2]
                n1 = float(slope[1]) #coefficients[3]
            else:
                k = 0.0
                n2 = 0.0
                n1 = 0.0 

            
            
            # ===================================================================================================================
            
            sfoc_trend_list = []

            sfoc_data = list(filter(lambda x:x['imo'] == str(i) ,all_me_data))   
            data_dict1 = {} 
            data_dict1['date'] = None
            
            if sfoc_data:
                data_dict1['id_vessel'] = sfoc_data[0]['id_vessel']

                try:
                    data_dict1['sfoc'] = round(float(sfoc_data[0]['sfoc']),2)
                except:
                    data_dict1['sfoc'] = sfoc_data[0]['sfoc']
            else:
                data_dict1['sfoc'] = None


            ij = 0
            while True:
                testy = None
                deviation = None
                try:
                    
                    testy = round(n1*float(sfoc_data[ij]['engine_load'])*float(sfoc_data[ij]['engine_load']) + n2*float(sfoc_data[ij]['engine_load']) + k)
                    deviation = ((sfoc_data[ij]["sfoc"]-testy)/ testy)*100
                    
                    break
                except IndexError:
                    break
                except Exception as e:
                    # print(e)
                    ij = ij+1
                    continue
                
            data_dict1['vessel_name'] = list(filter(lambda x: x['imo'] == i , mcr_data))[0]['name']
            fleet_name = list(filter(lambda x: x['imo'] == i , mcr_data))[0]['fleet_name']
            data_dict1['fleet'] ="Fleet "+ str(fleet_name)
            data_dict1['imo'] = i
            
            try:
                data_dict1['sfoc_shop'] = float(testy)
            except:
                data_dict1['sfoc_shop'] = testy
                
            try:
                data_dict1['deviation'] = round(deviation,2)
                if data_dict1['deviation'] >5 :
                    data_dict1['deviation_remarks'] = "Above 5% Limit"

                elif data_dict1['deviation'] < -5:
                    data_dict1['deviation_remarks'] = "Below 5% Limit"

                else:
                    data_dict1['deviation_remarks'] = "With in 5% Limit"
            except:
                data_dict1['deviation'] = deviation
                data_dict1['deviation_remarks'] = None


                
            
            sfoc_trend_list.append(data_dict1)

                

            # sfoc_data = list(filter(lambda x:x['imo'] == i ,all_me_data))
            # print(sfoc_data)
            # if not sfoc_data:
            #     print("1")

            #     return 0

            # engine_load = round(float(sfoc_data[0]['engine_load'])*2 )/2
            # engine_load_data = list(filter(lambda x:x['load'] == engine_load , sfoc_prediction))

            # if not engine_load_data:

            #     return 0

            # data_dict1 = {}
            # data_dict1 = {}
            # data_dict1['deviation'] = round(((float(sfoc_data[0]['sfoc']) - float(engine_load_data[0]['sfoc_predicted']))/float(engine_load_data[0]['sfoc_predicted']))*100)

            # if data_dict1['deviation'] >5 :
            #     data_dict1['deviation_remarks'] = "Above 5% Limit"

            # elif data_dict1['deviation'] < -5:
            #     data_dict1['deviation_remarks'] = "Below 5% Limit"

            # else:
            #     data_dict1['deviation_remarks'] = "With in 5% Limit"

            # sfoc_trend_list.append(data_dict1)



            # ---------------------------- SFOC End --------------------------------------------------------
            
          
            # return keydate_data
            key_date_sort = list(filter(lambda x:x['imo'] == i and  x['keydate_record'] == 'DD', keydate_data))
            
            if not key_date_sort:
                if data_dict1['deviation']:
                    avg_speed_data.append(data_dict1)
                return 0
            
          
            try:
                key_date_sort.sort(key = lambda x: datetime.strptime(x['date'], '%Y-%m-%dT%H:%M:%S%z') , reverse = True)

            except:
                key_date_sort.sort(key = lambda x: datetime.strptime(x['date'], '%Y-%m-%dT%H:%M:%S') , reverse = True)
            # print("-------------------------")
            # print(key_date_sort)
            # print("-------------------------")
            if key_date_sort[0]['end_dd_date']:
                try:
                    dry_dock_date =datetime.strptime (key_date_sort[0]['end_dd_date'], '%Y-%m-%dT%H:%M:%S%z')
                except:
                    dry_dock_date =datetime.strptime (key_date_sort[0]['end_dd_date'], '%Y-%m-%dT%H:%M:%S')
            else:
                try:
                    dry_dock_date =datetime.strptime (key_date_sort[0]['date'], '%Y-%m-%dT%H:%M:%S%z')
                except:
                    dry_dock_date =datetime.strptime (key_date_sort[0]['date'], '%Y-%m-%dT%H:%M:%S')
                    
            dry_dock_date_delta_check = dry_dock_date.strftime('%Y-%m-%d')

            delta = relativedelta(today, datetime.strptime(dry_dock_date_delta_check ,'%Y-%m-%d'))
            months_since_latest_dry_dock = delta.months + (delta.years * 12)
            years_since_latest_dry_dock = delta.years      
            # print(allvessel_data)
            try:
                mcr = float(list(filter(lambda x:x['imo']==str(i) and x['attribute_id'] == 148 , mcr_data))[0]['value'])
            except:
                if data_dict1['deviation']:
                    avg_speed_data.append(data_dict1)
                return 0
            
            try:
                scantling_draft = float(list(filter(lambda x:x['imo']==str(i) and x['attribute_id'] == 20 , mcr_data))[0]['value'])
            except:
                # if data_dict1['deviation']:
                #     avg_speed_data.append(data_dict1)
                # return 0
                scantling_draft = 0
                

            
            mcr_low = 0.15 * mcr
            mcr_high = 1.1 * mcr

            

            noon_datas = list(filter(lambda x:x['imo'] == i ,noon_data))

            if not noon_datas:
                if data_dict1['deviation']:
                    avg_speed_data.append(data_dict1)
                return 0
            
            speed_filter_data = list(filter(lambda x:x['imo'] == i , speed_filter))
            if speed_filter_data:
                min_speed = speed_filter_data[0]['stw_filter_min']
                max_speed = speed_filter_data[0]['stw_filter_max']
            
                    

                
                noon_datas = list(filter(lambda x:x[speed] != None , noon_datas))
                
                    
                noon_datas = list(filter(lambda x:float(x[speed]) <= max_speed and float(x[speed]) >= min_speed , noon_datas))
                
            else:

                noon_datas = list(filter(lambda x:float(x[speed]) != None , noon_datas))
                
                if not max_speed:
                    max_speed = 20
                noon_datas = list(filter(lambda x:float(x[speed]) <= (float(max_speed ) + 2 )and float(x[speed]) >= 10 , noon_data))
                

            
            if not noon_datas:
                if data_dict1['deviation']:
                    avg_speed_data.append(data_dict1)
                return 0
            df = pd.DataFrame.from_dict(noon_datas)
    
            df = df.fillna(value=0)
            # print(df)
            # df[speed] = df[speed].astype(float)
            # df[fuel] = df[fuel].astype(float)


            # df[speed] =  0 - df[speed]
            # df[fuel] =  0 - df[fuel]
            # df = df[(df[speed] <= 0) & (df[speed] >=-50)]
            # df = df[(df[fuel] > 0)]

            df['power_kw'] = pd.to_numeric(df['power_kw'])
            df['draft'] = pd.to_numeric(df['draft'])
            
            df = df[(df['draft'] <= scantling_draft)]

            if df.empty:
                if data_dict1['deviation']:
                    avg_speed_data.append(data_dict1)
                return 0
            df = df[(df.power_kw >= mcr_low) & (df.power_kw <=mcr_high)]
            
            if df.empty:
                if data_dict1['deviation']:
                    avg_speed_data.append(data_dict1)
                return 0
            try:
                df = df[(abs(df[speed_loss] - df[speed_loss].mean())) < (3*statistics.stdev(df[speed_loss]))]
            except:
                if data_dict1['deviation']:
                    avg_speed_data.append(data_dict1)
                return 0
            try:
                df = df[(abs(df[fuel] - df[fuel].mean())) < (3*statistics.stdev(df[fuel]))]
            except:
                if data_dict1['deviation']:
                    avg_speed_data.append(data_dict1)
                return 0
                
            if df.empty:
                if data_dict1['deviation']:
                    avg_speed_data.append(data_dict1)
                return 0


            df[speed_loss] = df[speed_loss].round(2)
            df[fuel] = df[fuel].round(2)
            df2 = pd.DataFrame()
            df2['Corrected_Date'] = pd.to_datetime( df['report_date_time']).dt.strftime('%Y-%m-%d %H:%M:%S')
            df2['speedloss'] = df[speed_loss]
            df2['fuelloss'] = df[fuel]
            df2 = df2.to_json(orient="records")
            speedloss_data_list = json.loads(df2)
            latest_speed_date =  datetime.strptime(datetime.now().strftime("%Y-%m-%d"), "%Y-%m-%d") 
            dry_dock_after = dry_dock_date + relativedelta(years=1)
            delta = relativedelta(latest_speed_date, datetime.strptime(dry_dock_date_delta_check ,'%Y-%m-%d'))
            after_diffr = (delta.years)

            if after_diffr <2 :
                middel_date  = dry_dock_date + (latest_speed_date - datetime.strptime(dry_dock_date_delta_check ,'%Y-%m-%d'))/2
                
            else:
                middel_date = dry_dock_after
           

            #print("test",str(dry_dock_date), speedloss_data_list)
            avg_data_left = (list(filter(lambda x:x['Corrected_Date'] <= str(middel_date) and x['Corrected_Date'] > str(dry_dock_date), speedloss_data_list)))

            avg_data_right = (list(filter(lambda x:x['Corrected_Date'] > str(middel_date) , speedloss_data_list)))

            if not avg_data_right or not avg_data_left:
                if data_dict1['deviation']:
                    avg_speed_data.append(data_dict1)
                return 0

            try:
                latest_speed_date = datetime.strptime (speedloss_data_list[-1]['Corrected_Date'], '%Y-%m-%d %H:%M:%S')
            except:
                latest_speed_date = datetime.strptime (speedloss_data_list[-1]['Corrected_Date'], '%Y-%m-%dT%H:%M:%S')



            avg_data_df_left = pd.DataFrame.from_dict(avg_data_left)
            avg_left_speed_value = round(avg_data_df_left['speedloss'].mean(),2)  
            avg_left_fuel_value = round(avg_data_df_left['fuelloss'].mean(),2)  
            avg_data_df_right = pd.DataFrame.from_dict(avg_data_right)
            avg_right_speed_value = round(avg_data_df_right['speedloss'].mean(),2)  
            avg_right_fuel_value = round(avg_data_df_right['fuelloss'].mean(),2)  

            # data_dict1 = {}

            data_dict1['imo'] = i
            data_dict1['Inservice PI'] = round( avg_right_speed_value - avg_left_speed_value,2)
            if avg_left_fuel_value == 0.0:
                data_dict1['fuelloss'] = 0
            else:
                data_dict1['fuelloss'] = round(avg_left_fuel_value - avg_right_fuel_value,2)
            if data_dict1['Inservice PI'] >= 0:
                data_dict1['speed_remarks'] = 'Speed Gain' 
            else:
                data_dict1['speed_remarks'] = 'Speed Loss' 

            if data_dict1['fuelloss'] >= 0:
                data_dict1['fuel_remarks'] = 'Fuel Gain' 
            else:
                data_dict1['fuel_remarks'] = 'Fuel Loss' 

            data_dict1['months_since_latest_dry_dock'] = months_since_latest_dry_dock


            data_dict1['years_since_latest_dry_dock'] = years_since_latest_dry_dock

            data_dict1['dry_dock_date'] = str(dry_dock_date)
            data_dict1['date'] = dry_dock_date.strftime('%d %b %Y')
        # mcr = list(filter(lambda x: x['attribute_id'] == 148 , allvessel_data))[0]['value']

            
            # try:
            # except:
            #     data_dict1['fleet'] = noon_datas[0]['fleet']
            data_dict1['dry_dock'] = key_date_sort[0]['intervention']
            data_dict1['keydate_record'] = key_date_sort[0]['keydate_record']
            # data_dict1['vessel_id'] = key_date_sort[0]['vessel_id']

            data_dict1['remarks'] = 'In service performance shows {}% {}& {} MT {}.'.format(data_dict1['Inservice PI'] ,data_dict1['speed_remarks'], data_dict1['fuelloss'],data_dict1['fuel_remarks'])

            

            avg_speed_data.append(data_dict1)
        
        avg_speed_data = []
        threads = []
        for i in imo_list:
                t = threading.Thread(target=data_handling, args=(i, avg_speed_data))
                t.start()
                threads.append(t)

            # Wait for all threads to complete
        for t in threads:
            t.join()
        
        result = json.dumps(avg_speed_data)
        state = await utility.set_data_async(key=CACHEKEY.HULLMONITORING_DASHBOARD_RESULT+str(fleet), value= result , seconds=604800)
    # result = result.replace("Nan", '0')
    try:
        result = result.replace("Nan", '0')
    except:
        pass   
    
    
   
    data = json.loads(result)
    
    def sort_key(entry):
        date_str = entry['date']
        if date_str is None:
            return datetime.min  # Use the minimum possible datetime for None dates
        return datetime.strptime(date_str, '%d %b %Y')

    # Sort the data
    data.sort(key=sort_key, reverse=True)

    # data.sort(key = lambda x: datetime.strptime(x['date'], '%d %b %Y'),reverse=True)

    return {'data':data , 'cache' :cache}





        
@router.get('/api/v1/vessel_count')
async def index(db : AsyncSession = Depends(get_db_async),vdm_db:AsyncSession = Depends(get_vdm_db_async),token : AsyncSession = Depends(get_token_async)):
    
    all_vessels = await cache_set.get_all_vsl_count(vdm_db)
    all_vessels_archive = await cache_set.get_all_vsl_count_archive(vdm_db)
    fleet = "8"
    sorrento = await cache_set.get_sorrento_vsl_count(vdm_db , fleet)
    sor_vessels_archive = await cache_set.get_sorrento_vsl_count_archive(vdm_db,fleet)
    
    fleet = "7"
    charter = await cache_set.get_charter_vsl_count(vdm_db , fleet)
    cha_vessels_archive = await cache_set.get_charter_vsl_count_archive(vdm_db,fleet)
    
    # df = pd.DataFrame(charter)    
    # fleet = 7get_fleet_wise
    # vessels = await cache_set.get_fleet_wise(vdm_db , fleet)
    
    # all_vessels = len(all_vessels)
    # sorrento = len(sorrento)
    # charter = len(charter)
    
    # all_vessels_archive = len(all_vessels_archive)
    # sor_vessels_archive = len(sor_vessels_archive)
    # cha_vessels_archive = len(cha_vessels_archive)
    
    
    
    
    return {
    "sorrento_vessels": [

        {

            "type": 'Present Vessels',

            "value": sorrento,

        },

        {

            "type": 'Archived Vessels',

            "value": sor_vessels_archive,

        },

    ],

    "charter_vessels": [

        {

            "type": 'Present Vessels',

            "value": charter,

        },

        {

            "type": 'Archived Vessels',

            "value": cha_vessels_archive,

        },

    ],

    "MSC_SM_vessels": [

        {
            "type": 'Present Vessels',
            "value": all_vessels,
        },
        {
            "type": 'Archived Vessels',
            "value": all_vessels_archive,
        },
    ]}

async def get_current_year_cii_year(db , year,fleet,vessel_list,mcr_data,vdm_db):
    if int(year) == 2022:
        year_factor = 0.03
    elif int(year) == 2023:
        year_factor = 0.05
    elif int(year) == 2024:
        year_factor = 0.07
    elif int(year) == 2025:
        year_factor = 0.09
    elif int(year) == 2026:
        year_factor = 0.11
    else:
        return []


    if not fleet:

        fleet = 'All'

    data_dict = {item['imo']: {'dwt': '', 'ship_type': '', 'ship_name': '' , 'gross_tonage':''} for item in mcr_data}
    
    for item in mcr_data:
        
        data_dict[item['imo']][{8: 'dwt', 4: 'ship_type', 61: 'ship_name' ,83:'gross_tonage'}.get(item['attribute_id'])] = item['value']
        
    # return data_dict
    
    vessel_types = await cache_set.get_vessel_types(vdm_db)
    vessel_types = {item['id']: item['name'] for item in vessel_types}

    
    data2 = []
    # print(mcr_data)
    for i , j in data_dict.items():
        # print("i:",i,"j:",j)
        vessel_data_dict = {}
        vessel_data_dict['imo'] = i
        vessel_data_dict['fleet'] = list(filter(lambda x : x['imo'] == i , mcr_data))[0]['fleet']
        vessel_data_dict['dwt'] = j['dwt']
        
        vessel_data_dict['type'] = vessel_types[int(j['ship_type'])]
        
        # if j['ship_type'] == '1':
        #     vessel_data_dict['type'] = 'Container'
        # elif j['ship_type'] == '2':
        #     vessel_data_dict['type'] = 'Bulk Carrier'
        # elif j['ship_type'] == '5':
        #     vessel_data_dict['type'] = 'ROPAX' 
        # elif j['ship_type'] == '4':
        #     vessel_data_dict['type'] = 'PAX' 
        # elif j['ship_type'] == '3':
        #     vessel_data_dict['type'] = 'PCTC'
        # elif j['ship_type'] == '6':
        #     vessel_data_dict['type'] = 'TUG'                    
        vessel_data_dict['name'] = list(filter(lambda x : x['imo'] == i , mcr_data))[0]['name']
       
        vessel_data_dict['gross_tonage'] =  j['gross_tonage']
     
        
        data2.append(vessel_data_dict)


    data = await cache_set.get_data_for_cii(db , vessel_list,str(year),fleet)
    if not data: 
        return []
    
    df=pd.DataFrame.from_dict(data)
    df_data=pd.DataFrame.from_dict(data2)
    df[['fuel_me_rsdl_hs' , 'fuel_aux_rsdl_hs' , 'fuel_boiler_rsdl_hs',"fuel_me_rsdl_vls",'fuel_aux_rsdl_vls','fuel_boiler_rsdl_vls','fuel_me_rsdl_uls','fuel_aux_rsdl_uls','fuel_boiler_rsdl_uls','fuel_me_dstlt_vls' , 'fuel_aux_dstlt_vls' , 'fuel_boiler_dstlt_vls','fuel_me_dstlt_uls' ,'fuel_aux_dstlt_uls' , 'fuel_boiler_dstlt_uls','fuel_me_tnktnr_dstlt_vls' , 'fuel_aux_tnktnr_dstlt_vls','fuel_boiler_tnktnr_dstlt_vls']]=df[['fuel_me_rsdl_hs' , 'fuel_aux_rsdl_hs' , 'fuel_boiler_rsdl_hs',"fuel_me_rsdl_vls",'fuel_aux_rsdl_vls','fuel_boiler_rsdl_vls','fuel_me_rsdl_uls','fuel_aux_rsdl_uls','fuel_boiler_rsdl_uls','fuel_me_dstlt_vls' , 'fuel_aux_dstlt_vls' , 'fuel_boiler_dstlt_vls','fuel_me_dstlt_uls' ,'fuel_aux_dstlt_uls' , 'fuel_boiler_dstlt_uls','fuel_me_tnktnr_dstlt_vls' , 'fuel_aux_tnktnr_dstlt_vls','fuel_boiler_tnktnr_dstlt_vls']].apply(pd.to_numeric)
    df['total_hs'] =  df[['fuel_me_rsdl_hs' , 'fuel_aux_rsdl_hs' , 'fuel_boiler_rsdl_hs']].sum(axis=1)
    
    #Total LS
    df['total_ls'] =  df[["fuel_me_rsdl_vls",'fuel_aux_rsdl_vls','fuel_boiler_rsdl_vls','fuel_me_rsdl_uls','fuel_aux_rsdl_uls','fuel_boiler_rsdl_uls']].sum(axis = 1)
    
    #Total ULS
    df['total_uls'] =  df[['fuel_me_dstlt_vls' , 'fuel_aux_dstlt_vls' , 'fuel_boiler_dstlt_vls','fuel_me_dstlt_uls' ,'fuel_aux_dstlt_uls' , 'fuel_boiler_dstlt_uls','fuel_me_tnktnr_dstlt_vls' , 'fuel_aux_tnktnr_dstlt_vls','fuel_boiler_tnktnr_dstlt_vls']].sum(axis=1)
    df[['total_hs' , 'total_ls' , 'total_uls'  ]]=df[['total_hs' , 'total_ls' , 'total_uls'  ]].apply(pd.to_numeric)
    df['total_fuel'] = df[['total_hs' , 'total_ls' , 'total_uls'  ]].sum(axis=1)
    
    df['total_hs_co_2'] = (df["total_hs"])*3.114
    df['total_ls_co_2'] = df["total_ls"]*3.151
    df['total_uls_co_2'] = df["total_uls"]*3.206
    df.drop('total_co2',inplace = True ,axis = 1)
    
    df['total_co2'] = df[['total_hs_co_2', 'total_uls_co_2','total_ls_co_2'] ].sum(axis = 1)  
    data_sort = df.merge(df_data, on='imo', how='left').sort_values(by=['imo','report_date_time'],ascending=True)
    
    
    # data_sort['report_date_time'] = pd.to_datetime(data_sort['report_date_time'],format='%Y-%m-%dT%H:%M:%S%z')
    # data_sort['Month_name'] = data_sort['report_date_time'].dt.strftime('%B')
    # data_sort['Month'] = data_sort['report_date_time'].dt.strftime('%b')
    # data_sort['Year'] = data_sort['report_date_time'].dt.strftime('%Y')
    # data_sort['Date'] = data_sort['report_date_time'].dt.strftime('%d')
    data_sort['Year'] = data_sort['report_date_time'].str[:4]

    data_sort = data_sort.replace("", 0)
    # if (data_sort['type'] == 'Container').any():
    #     #Total HS,LS,MGO and Total Fuel
    #     convert_dict = {
    #                 'fuel_me_rsdl_hs': float,
    #                 'fuel_aux_rsdl_hs': float,
    #                 'fuel_boiler_rsdl_hs': float,
    #                 'fuel_me_rsdl_vls': float,
    #                 'fuel_me_rsdl_uls': float,
    #                 'fuel_aux_rsdl_vls': float,
    #                 'fuel_aux_rsdl_uls':float,
    #                 'fuel_boiler_rsdl_vls':float,
    #                 'fuel_boiler_rsdl_uls':float,
    #                 'fuel_me_dstlt_vls':float,
    #                 'fuel_me_dstlt_uls':float,
    #                 'fuel_me_tnktnr_dstlt_vls':float,
    #                 'fuel_aux_dstlt_vls':float,
    #                 'fuel_aux_dstlt_uls':float,
    #                 'fuel_aux_tnktnr_dstlt_vls':float,
    #                 'fuel_boiler_dstlt_vls':float,
    #                 'fuel_boiler_dstlt_uls':float,
    #                 'reefers_positive_plugged':float,    
    #                 'reefers_negative_plugged':float,
    #                 "miles_by_gps":float,
    #                 "total_co2":float,
    #                 "dwt":float,
    #                 "gross_tonage":float,
    #                 "fuel_boiler_tnktnr_dstlt_vls":float 
    #                 }
    #     data_sort = data_sort.astype(convert_dict) 
        
    #     data_sort['total_hs'] =  data_sort[['fuel_me_rsdl_hs' , 'fuel_aux_rsdl_hs' , 'fuel_boiler_rsdl_hs']].sum(axis=1)
    #     #Total LS
    #     data_sort['total_ls'] =  data_sort[["fuel_me_rsdl_vls",'fuel_aux_rsdl_vls','fuel_boiler_rsdl_vls','fuel_me_rsdl_uls','fuel_aux_rsdl_uls','fuel_boiler_rsdl_uls']].sum(axis = 1)
    #     #Total ULS
    #     data_sort['total_uls'] =  data_sort[['fuel_me_dstlt_vls' , 'fuel_aux_dstlt_vls' , 'fuel_boiler_dstlt_vls','fuel_me_dstlt_uls' ,'fuel_aux_dstlt_uls' , 'fuel_boiler_dstlt_uls','fuel_me_tnktnr_dstlt_vls' , 'fuel_aux_tnktnr_dstlt_vls','fuel_boiler_tnktnr_dstlt_vls']].sum(axis=1)
    #     data_sort['total_fuel'] = data_sort[['total_hs' , 'total_ls' , 'total_uls'  ]].sum(axis=1)
    #     data_sort['status'] = data_sort['status'].ffill().str.replace("DRIFTING", "AT SEA")
    #     data_sort['total_hs_co_2'] = (data_sort["total_hs"])*3.114
    #     data_sort['total_ls_co_2'] = data_sort["total_ls"]*3.151
    #     data_sort['total_uls_co_2'] = data_sort["total_uls"]*3.206
    #     data_sort['total_co2'] = data_sort[['total_hs_co_2', 'total_uls_co_2','total_ls_co_2'] ].sum(axis = 1)  
        
    #     # Calculating Fuel Consumption
    #     #Total ME
    #     data_sort['total_me_fuel'] = data_sort[['fuel_me_rsdl_hs' , 'fuel_me_rsdl_vls','fuel_me_rsdl_uls','fuel_me_dstlt_vls' , 'fuel_me_dstlt_uls' , 'fuel_me_tnktnr_dstlt_vls'  ]].sum(axis=1) 
    #     #Total LS
    #     data_sort['total_ae_fuel'] =  data_sort[['fuel_aux_rsdl_hs' , 'fuel_aux_rsdl_vls' , 'fuel_aux_rsdl_uls','fuel_aux_dstlt_vls' , 'fuel_aux_dstlt_uls' , 'fuel_aux_tnktnr_dstlt_vls']].sum(axis=1) 
    #     #Total Boiler
    #     data_sort['total_boiler_fuel'] =  data_sort[['fuel_boiler_rsdl_hs' , 'fuel_boiler_rsdl_vls' , 'fuel_boiler_rsdl_uls','fuel_boiler_dstlt_vls', 'fuel_boiler_dstlt_uls' , 'fuel_boiler_tnktnr_dstlt_vls'  ]].sum(axis=1)
    #     data_sort['me_hs_co_2'] = data_sort[['fuel_me_rsdl_hs'   ]].sum(axis=1) *3.114
    #     data_sort['me_ls_co_2'] = data_sort[['fuel_me_rsdl_vls','fuel_me_rsdl_uls']].sum(axis=1) *3.151
    #     data_sort['me_uls_co_2'] = data_sort[[ 'fuel_me_dstlt_vls' , 'fuel_me_dstlt_uls' , 'fuel_me_tnktnr_dstlt_vls'  ]].sum(axis=1) *3.206
    #     data_sort['ae_hs_co_2'] = data_sort[['fuel_aux_rsdl_hs'  ]].sum(axis=1) *3.114
    #     data_sort['ae_ls_co_2'] = data_sort[[ 'fuel_aux_rsdl_vls' , 'fuel_aux_rsdl_uls'  ]].sum(axis=1) *3.151
    #     data_sort['ae_uls_co_2'] = data_sort[[ 'fuel_aux_dstlt_vls' , 'fuel_aux_dstlt_uls' , 'fuel_aux_tnktnr_dstlt_vls'  ]].sum(axis=1) *3.206
    #     data_sort['boiler_hs_co_2'] = data_sort[['fuel_boiler_rsdl_hs'    ]].sum(axis=1)*3.114
    #     data_sort['boiler_ls_co_2'] = data_sort[[  'fuel_boiler_rsdl_vls' , 'fuel_boiler_rsdl_uls'  ]].sum(axis=1)*3.151
    #     data_sort['boiler_uls_co_2'] = data_sort[[ 'fuel_boiler_dstlt_vls' , 'fuel_boiler_dstlt_uls' , 'fuel_boiler_tnktnr_dstlt_vls'  ]].sum(axis=1)*3.206
        
    #     data_sort['total_me_co_2'] = data_sort[['me_hs_co_2' , 'me_ls_co_2', 'me_uls_co_2'] ].sum(axis = 1)  
    #     data_sort['total_ae_co_2'] = data_sort[['ae_hs_co_2' , 'ae_ls_co_2', 'ae_uls_co_2'] ].sum(axis = 1)  
    #     data_sort['total_boiler_co_2'] = data_sort[['boiler_hs_co_2' , 'boiler_ls_co_2', 'boiler_uls_co_2'] ].sum(axis = 1)  
    #     data_sort['Total Reefer']=data_sort['reefers_positive_plugged']+data_sort['reefers_negative_plugged']
    #     data_sort['Total Reefer']=data_sort['Total Reefer'].ffill() 
    #     data_sort['status'] = data_sort['status'].replace("DRIFTING", "AT SEA")
    #     data_sort['report_date_time'] = pd.to_datetime(data_sort['report_date_time'])
    #     data_sort['time_diff'] = data_sort['report_date_time'].diff()
    #     data_sort['time_diff'] = data_sort['time_diff'].shift(-1)
    #     data_sort['status_change'] = 0
    #     current_value = None
    #     counter = 0
    #     for index, row in data_sort.iterrows():
    #         if row['status'] != current_value:
    #             current_value = row['status']
    #             counter += 1
    #         data_sort.at[index, 'status_change'] = counter
    #     # Mean of reefers for At sea condition
    #     data_sort['consecutive_mean'] = data_sort['Total Reefer'].rolling(window=2).mean()
    #     data_sort= data_sort.bfill()

    #     data_sort['Port_Mean'] = 0

    #     b_indices = data_sort.index[data_sort['status'] == 'IN PORT'].tolist()

    #     for b_index in b_indices:
    #         before_a_index = data_sort[data_sort['status'] == 'AT SEA'].index[data_sort[data_sort['status'] == 'AT SEA'].index < b_index].max()
    #         after_a_index = data_sort[data_sort['status'] == 'AT SEA'].index[data_sort[data_sort['status'] == 'AT SEA'].index > b_index].min()

    #         if pd.notna(before_a_index) and pd.notna(after_a_index):
    #             avg_reefer = data_sort.loc[[before_a_index, after_a_index]]['Total Reefer'].mean()

    #             data_sort.at[b_index, 'Port_Mean'] = avg_reefer

    #     # data_sort=data_sort[[ 'imo','fleet','name',  'Year','total_co2',"miles_by_gps" , "dwt" , "type","gross_tonage"]]
    #     data_sort['dwt'] =np.where(data_sort['type'] == 'Container', data_sort['dwt'], data_sort['gross_tonage'])
    #     data_sort = data_sort.replace('NaT', 0)
    #     data_sort = data_sort.replace("", 0)
    #     data_sort= data_sort[data_sort['dwt'] != 0.0]
        
    #     Noon_gp = data_sort.groupby(['imo', 'name', 'type', 'Year', 'fleet','status_change']).agg({'total_co2':np.sum,'miles_by_gps':np.sum,'dwt':np.mean,'time_diff': np.sum, 'consecutive_mean': 'last', 'status': 'first','Port_Mean':'last','total_hs': np.sum,'total_ls': np.sum,'total_uls': np.sum,'total_fuel': np.sum,'total_hs_co_2': np.sum,'total_ls_co_2': np.sum,'total_uls_co_2': np.sum}).reset_index()
    #     Noon_gp['time_diff'] = pd.to_timedelta(Noon_gp['time_diff'])

    #     Noon_gp['time_diff_numeric'] = Noon_gp['time_diff'].dt.days + Noon_gp['time_diff'].dt.seconds / (24 * 60 * 60)
    #     mask = Noon_gp["status"] == "AT SEA"

    #     Noon_gp["total_reefer_time"] = np.where(mask, Noon_gp["consecutive_mean"] * Noon_gp["time_diff_numeric"], Noon_gp["Port_Mean"] * Noon_gp["time_diff_numeric"])

    #     Noon_gp = Noon_gp.sort_values(by='status_change')

    #     # total_co2=("total_co2", "sum"),miles_by_gps=("miles_by_gps", "sum"),dwt=("dwt", "mean")
    #     Noon_gp['reefer_fuel'] = np.where(mask, 2.75 * 24 *190* Noon_gp[ 'consecutive_mean']/1000000, 2.75 * 24 *190* Noon_gp['Port_Mean']/1000000)



    #     Noon_gp['hs_reefers'] = Noon_gp['reefer_fuel'] * Noon_gp['total_hs'] / Noon_gp['total_fuel'] 
    #     Noon_gp['ls_reefers'] = Noon_gp['reefer_fuel'] * Noon_gp['total_ls'] / Noon_gp['total_fuel'] 
    #     Noon_gp['uls_reefers'] = Noon_gp['reefer_fuel'] * Noon_gp['total_uls'] / Noon_gp['total_fuel'] 

    #     Noon_gp['hs_co2_reefers'] = (Noon_gp['hs_reefers'] *   3.114 * 0.75 )* year_factor
    #     Noon_gp['ls_co2_reefers'] = (Noon_gp['ls_reefers'] *   3.151 * 0.75 )* year_factor
    #     Noon_gp['uls_co2_reefers'] = (Noon_gp['uls_reefers'] * 3.206 * 0.75 )* year_factor


    #     Noon_gp['total_co2_reefers'] = Noon_gp[['hs_co2_reefers' , 'ls_co2_reefers' , 'uls_co2_reefers']].sum(axis = 1)
    #     Noon_gp['actual_co2']   = Noon_gp['total_co2']  -  Noon_gp['total_co2_reefers'] 
        
    #     distance =Noon_gp['miles_by_gps'].sum()
        
    #     Noon_gp["Attained_CII"]= (Noon_gp['actual_co2'])  * 1000000/(Noon_gp['dwt']*(distance) )
        
    # else:
    convert_dict = {
            "miles_by_gps":float,
            "total_co2":float,
            "dwt":float,
            "gross_tonage":float
            }
    data_sort = data_sort.astype(convert_dict)
    data_sort=data_sort[[ 'imo','fleet','name',  'Year','total_co2',"miles_by_gps" , "dwt" , "type","gross_tonage"]]
    data_sort['dwt'] =np.where((data_sort['type'] == 'Container')|(data_sort['type'] == 'Bulk Carrier'), data_sort['dwt'], data_sort['gross_tonage'])
    data_sort= data_sort.fillna(0)
    data_sort = data_sort.replace("", 0)
    data_sort= data_sort[data_sort['dwt'] != 0.0]
    Noon_gp = data_sort.groupby(['imo', 'name', 'type', 'Year', 'fleet']).agg( total_co2=("total_co2", "sum"),miles_by_gps=("miles_by_gps", "sum"),dwt=("dwt", "mean")).reset_index()
    Noon_gp["Attained_CII"]=((Noon_gp["total_co2"]*(10**6))/(Noon_gp["miles_by_gps"]*Noon_gp["dwt"])).round(2)
    


    
    if not Noon_gp.empty:

        def rqrd_cii(x,y,z):

            
            if y=='Container':
                return (1984*(x)**-0.489)
            elif y=='Bulk Carrier':
                if (x>=279000):
                    return (4745*(279000)**-0.622)
                else:
                    return (4745*(x)**-0.622)
            elif y=='ROPAX':
                return (7540*(x)**-0.587)
            else:#roro cargo ship(vehicle carrier)
                return (5739*(x)**-0.631)
    
        Noon_gp['Required_CII'] = Noon_gp.apply(lambda x: rqrd_cii(x['dwt'], x["type"],x['imo']), axis=1)
        Noon_gp["Required_CII_percent"] = Noon_gp["Required_CII"]*year_factor
        Noon_gp["Required_CII"] = Noon_gp["Required_CII"]-Noon_gp["Required_CII_percent"]
        Noon_gp["A/R"]=Noon_gp["Attained_CII"]/Noon_gp["Required_CII"]
        Noon_gp=Noon_gp.round({"A/R":2})
        

        def rating(y,z):
            if z=='Container' and y != float("inf"):
                if y>=0 and y<=0.83 :
                    return "A"
                elif y>0.83 and y<=0.94 :
                    return "B"
                elif y>0.94 and y<=1.07 :
                    return "C"
                elif y>1.07 and y<=1.19 :
                    return "D"
                elif y>1.19 :
                    return "E"
                
            elif z=='ROPAX'and y != float("inf"):
                if y>=0 and y<=0.72 :
                    return "A"
                elif y>0.72 and y<=0.90 :
                    return "B"
                elif y>0.90 and y<=1.12 :
                    return "C"
                elif y>1.12 and y<=1.41 :
                    return "D"
                elif y>1.41 :
                    return "E"
                
            elif z=='Bulk Carrier'and y != float("inf"):
                if y>=0 and y<=0.86 :
                    return "A"
                elif y>0.86 and y<=0.94 :
                    return "B"
                elif y>0.94 and y<=1.06 :
                    return "C"
                elif y>1.06 and y<=1.18 :
                    return "D"
                elif y>1.18 :
                    return "E"
                
            elif y != float("inf"): 
                if y>=0 and y<=0.86 :
                    return "A"
                elif y>0.86 and y<=0.94 :
                    return "B"
                elif y>0.94 and y<=1.06 :
                    return "C"
                elif y>1.06 and y<=1.16 :
                    return "D"
                elif y>1.16 :
                    return "E"
                
            else:
                 return ""   
        Noon_gp=Noon_gp.round(2)
        Noon_gp['Rating'] = Noon_gp.apply(lambda x: rating(x['A/R'],x["type"]), axis=1)
        
      
    

    
    Noon_gp=Noon_gp[["name", 'fleet','imo', 'Year',"A/R","Rating","dwt",
                                        'miles_by_gps','total_co2','Required_CII','Attained_CII','type']]

    Noon_gp=Noon_gp.rename({"dwt":"deadweight","Required_CII":"required_cii",
                                          "Rating":"attained_rating","miles_by_gps":"sailed_distance",
                                          "type":"vessel_type","Attained_CII":"attained_cii","Year":"year",
                                          "A/R":"a_r","Fleet":"fleet" , "name":"vessel_name"},axis=1)

                                          
    Noon_gp=Noon_gp[["total_co2","deadweight","vessel_name","required_cii","attained_rating",
                                    "sailed_distance","vessel_type","imo","attained_cii","year","a_r","fleet"]]
    Noon_gp=Noon_gp.round(2)
    Noon_gp.rename(columns = {'total_co2' : 'total_co_2'} , inplace = True)
    Noon_gp["year"]=Noon_gp["year"].astype(str)
    # Noon_gp['fleet'] = "Fleet "+ Noon_gp["fleet"]
   
    Noon_gp = Noon_gp.to_json(orient = 'records')
    dict_Bulker_Tanker = json.loads(Noon_gp)
    # return dict_Bulker_Tanker
    data_dict = []

    for i in dict_Bulker_Tanker:
        try:
            i['attained_rating'] = list(i['attained_rating'])
        except:
            i['attained_rating'] = None
        # i['fleet'] = int(i["fleet"])
        i['fleet'] = str(i["fleet"])

        
        data_dict.append(i)

    return data_dict

async def cii_yearly_data_cacl(db,vdm_db,fleet):
    if not fleet:
        fleet = 'All'
        
    attributes_id = [4,8,61,83]
    
    mcr_data = await cache_set.get_all_vdm_vessel_attribute(vdm_db)
    
    if fleet == 'All':
        # mcr_data = await cache_set.get_mcr_filter(vdm_db)
        mcr_data = list(filter(lambda x:x['attribute_id'] in attributes_id, mcr_data))
        
        pass
    else:
        # mcr_data = await cache_set.get_mcr_filter_for_all(vdm_db ,fleet)
        mcr_data = list(filter(lambda x:x['fleet'] == int(fleet) and x['attribute_id'] in attributes_id, mcr_data))
    if not mcr_data:
        return {'data':[],'error':'No data mcr_data'}    
    vessel_list_fleet= [i['imo'] for i in mcr_data]
    vessel_list_fleet = set(vessel_list_fleet)
    vessel_list = list(vessel_list_fleet)

    data = await cache_set.get_cii_yearly(db,fleet,vessel_list)

    data = pd.DataFrame(data)
    if fleet == 'All':
        if 'imo' in mcr_data and 'imo' in data:
            data['fleet'] = data.loc[data['imo'].isin(mcr_data['imo']), 'imo'].map(mcr_data.set_index('imo')['fleet_name'])
            data['vessel_name'] = data.loc[data['imo'].isin(mcr_data['imo']), 'imo'].map(mcr_data.set_index('imo')['name'])
    else:

        data['fleet'] = mcr_data[0]['fleet_name']
    data=data[data['vessel_name']!=0]  
   
    data['year'] = data['year'].astype(str)
    data['fleet'] = data['fleet'].astype(str)
    data = data.to_json(orient="records")
    data = json.loads(data)
    year  = datetime.today().year
    current_year_data = await get_current_year_cii_year(db , year,fleet,vessel_list,mcr_data,vdm_db)

    data = data + current_year_data

    return data


# @router.get('/api/v1/cii/yearly')
# @router.get('/cii/yearly')
# def index(db : AsyncSession = Depends(get_db_async),token :AsyncSession= Depends(get_token_async)):
#     cii_yearwise_data = await cache_set.get_cii_yearly_count(db,'All',None)
#     cii_fleetwise_data = await cache_set.get_cii_fleet(db)
#     print(cii_yearwise_data)
#     # cii_yearwise_data = sorted(cii_yearwise_data, key=lambda x: (x['year'],x['attained_rating']))
#     cii_yearwise_data = sorted(
#     cii_yearwise_data,
#     key=lambda x: (
#         x['year'] if x['year'] is not None else '',  # Provide a default value for None in 'year'
#         x['attained_rating'] if x['attained_rating'] is not None else ''  # Provide a default value for None in 'attained_rating'
#     )
# )

#     cii_yearwise = list(filter(lambda x:x['year'] == cii_yearwise_data[-1]['year'] ,cii_yearwise_data))
#     cii_yearwises = json.dumps(cii_yearwise)
#     year = cii_yearwise[0]['year']

#     befor_data = '"year": "{}"'.format(year)
#     for _ in range(0,3):
#         year = int(year)+1
#         year = str(year)
#         replace_data = '"year": "{}"'.format(year)
#         cii_year = cii_yearwises.replace(befor_data,replace_data)
#         cii_year = json.loads(cii_year)
#         cii_yearwise_data = cii_yearwise_data + cii_year
#     # cii_fleetwise_data = sorted(cii_fleetwise_data, key=lambda x: (x['fleet'],x['year'],x['attained_rating']))
#     cii_fleetwise_data = sorted(
#     cii_fleetwise_data,
#     key=lambda x: (
#         x['fleet'] if x['fleet'] is not None else '',
#         x['year'] if x['year'] is not None else '',
#         x['attained_rating'] if x['attained_rating'] is not None else ''
#     )
# )
    
#     return {"data":{"year_wise" : cii_yearwise_data  , "fleet_wise" : cii_fleetwise_data }}  

@router.get('/api/v1/cii/yearly')
@router.get('/cii/yearly')
async def index(vdm_db : AsyncSession = Depends(get_vdm_db_async),db : AsyncSession = Depends(get_db_async),token :AsyncSession= Depends(get_token_async)):
    vdm_data=await cache_set.get_all_vdm_vessel_attribute(vdm_db)

    cii_yearwise_data = await cache_set.get_cii_yearly_count(db,'All',None)
    # cii_fleetwise_data = await cache_set.get_cii_fleet(db)

    date2 = datetime.now()
    cii_daily = await cache_set.get_cii_daily_complete(db,date2.year)
    # cii_yearwise_data = json.dumps(cii_yearwise_data)
    # cii_yearwise_data = json.loads(cii_yearwise_data)

    # year = cii_yearwise[0]['year']    

    year=date2.year
    # date1=str(date(int(date2.year) ,1 ,1))
    # befor_data = '"year": "{}"'.format(year)
    noondata_set=pd.DataFrame(cii_daily)
    if noondata_set.empty:
            return {"data":[]}
    # noondata_complete=pd.DataFrame()

    noondata_set['year']=str(date2.year)
    noondata_set['date'] = pd.to_datetime(noondata_set['date'],format='%Y-%m-%d')

    if noondata_set.empty:
        return {"data":[]}
    # imo_list=set(list(noondata_set['imo']))
    # Filter the DataFrame using a lambda function
    vdm_data = pd.DataFrame(vdm_data)

    # filtered_vdm_data = vdm_data[vdm_data.apply(lambda x: x['imo'] in imo_list, axis=1)]
    imo_fleetlist=vdm_data[['imo','fleet']]
    imo_fleetlist = imo_fleetlist.drop_duplicates()
    imo_fleet_mapping = imo_fleetlist.set_index('imo')['fleet']
    noondata_set['fleet'] = noondata_set['imo'].map(imo_fleet_mapping)

    
    noondata_set = noondata_set.groupby(['imo','vessel_type','year','fleet']).agg({'miles_by_gps':np.sum,'total_co2': np.sum,'dwt':np.mean,'required_cii':np.mean}).reset_index()
    noondata_set['attained_cii'] = noondata_set['total_co2']*1E6/(noondata_set['dwt'] * noondata_set['miles_by_gps']*1)
    noondata_set['a_r'] = 0

    noondata_set['a_r'] = noondata_set['attained_cii']/noondata_set['required_cii']
    noondata_set['attained_rating'] = noondata_set.apply(lambda x: rating(x.a_r,x.vessel_type), axis=1)
    noondata_set = noondata_set.groupby(['year', 'attained_rating','fleet']).size().reset_index(name='count')
    noondata_set = noondata_set.to_dict(orient="records")  

    cii_yearwise_data=cii_yearwise_data+noondata_set
    cii_yearwise_data = pd.DataFrame(cii_yearwise_data)
    cii_yearwise_data['year'] =  pd.to_datetime(cii_yearwise_data['year'],format='%Y')
    grouped = cii_yearwise_data.groupby('attained_rating')

    
    predictions = {}
    for rating_s, group in grouped:
        group = group.set_index('year').resample('Y').sum()
        group.index = group.index.year
        # group = group.groupby(['year','attained_rating','fleet']).sum().reset_index()
        group['counts'] = np.log(group['count'])
        model = ARIMA(group['counts'], order=(1, 1, 1))
        model_fit = model.fit()
        forecast_log = model_fit.forecast(steps=6)
        forecast = np.exp(forecast_log)
        predictions[rating_s] = forecast

    predictions_df = pd.DataFrame(predictions)
    predictions_df.index = [2025, 2026, 2027,2028,2029,2030]
    
    
    currect_vessel_count = cii_yearwise_data[cii_yearwise_data['year']=='2024-01-01']['count'].sum(numeric_only=True)

    # Adjust predictions to match the desired total vessel count
    for year in predictions_df.index:
        current_sum = predictions_df.loc[year].sum()
        
        adjustment_factor = currect_vessel_count / current_sum
        predictions_df.loc[year] = predictions_df.loc[year] * adjustment_factor
    
    # Convert predictions to integers
    predictions_df = predictions_df.astype(int)
    cii_yearwise_data['year'] = cii_yearwise_data['year'].dt.year.astype(str)
    pie_chart =  cii_yearwise_data.groupby(['year','attained_rating']).agg({'count':sum}).reset_index()
    pie_chart_data = pie_chart.to_json(orient="records")
    pie_chart_data = json.loads(pie_chart_data)

    df_transformed = predictions_df.stack().reset_index()
    df_transformed.columns = ['year', 'attained_rating', 'count']
    perc_df = pd.concat([pie_chart,df_transformed])
    perc_df['total_count'] = perc_df.groupby('year')['count'].transform('sum')
    perc_df['rating'] = round((perc_df['count'] / perc_df['total_count'])*100,2)
    perc_df = perc_df.drop(columns=['total_count'])
    perc_data = perc_df.to_json(orient="records")
    perc_data = json.loads(perc_data)
    print(cii_yearwise_data)
    cii_yearwise_data = pd.concat([cii_yearwise_data,df_transformed])
    cii_yearwise_data['year'] = cii_yearwise_data['year'].astype(str)
    data = cii_yearwise_data.to_json(orient="records")
    data = json.loads(data)
    return {"data":{ "year_wise" : data ,"pie_chart":pie_chart_data,"cii_perc":perc_data}}

@router.get('/api/v1/cii/yearly_data/{fleet}')
@router.get('/api/v1/cii/yearly_data')
async def index(fleet:str = None,db: AsyncSession = Depends(get_db_async),vdm_db: AsyncSession = Depends(get_vdm_db_async),token : AsyncSession = Depends(get_token_async)):
    data = await utility.get_data_async(key=CACHEKEY.FINAL_RESULT_CIIYEARLYDATA)
    cache = False
    if data is not None:

        cache = True
        print("from cache")
    else:
        data = await cii_yearly_data_cacl(db,vdm_db,'All')
        

        
        try:
                if data is not None:
                    cache = False
                    data = json.dumps(jsonable_encoder(data))
                    state = await utility.set_data_async(key=CACHEKEY.FINAL_RESULT_CIIYEARLYDATA, value= data,seconds=604800)
                    
                
                    if state is True:
                            print('Cache Set Successfully') 

        except Exception as e:
                print(e)
                print('cache set failure')

    data = json.loads(data)
    
    if fleet != 'ALL' and fleet !='All':
        
        if int(fleet) >= 10:
            fleet = str(int(fleet) - 3)
            data = list(filter(lambda x:x['fleet'] == str(fleet) and x['vessel_name']!=0 , data))
        else:
            data = list(filter(lambda x:x['fleet'] == str(fleet) and x['vessel_name']!=0 , data))
             


            # ========================================================================================
        
            
            
        return data


async def cii_all_fleet_cal(db,vdm_db):
    mcr_data = await cache_set.get_all_vdm_vessel_attribute(vdm_db)
    
    if not mcr_data:
        return {'data':[],'error':'No data mcr_data'}    
    vessel_list_fleet= [i['imo'] for i in mcr_data]
    vessel_list_fleet = set(vessel_list_fleet)
    vessel_list = list(vessel_list_fleet)
    # vessel_list = list(mcr_data['imo'])
    # data = await cache_set.get_cii_yearly(db,'All',vessel_list)

    # data = pd.DataFrame(data)
    

    # data['year'] = data['year'].astype(str)
    # data = data.to_json(orient="records")
    # data = json.loads(data)
    year  = datetime.today().year
    print("Getting noondata")
    # mcr_data = mcr_data.to_json(orient='records')
    # mcr_data = json.loads(mcr_data)
    # return mcr_data
    data = await get_current_year_cii_year(db , year,'All',vessel_list,mcr_data,vdm_db)
    if not data:
        return []
    print("Getting noondata Completed")
    
    

    # data = data + current_year_data
    df=pd.DataFrame(data)
    mcr_data = pd.DataFrame(mcr_data)
    df = df.drop(columns=['fleet'])
    df = pd.merge(df, mcr_data[['imo', 'fleet_name']], on='imo', how='left')
    df.rename(columns={'fleet_name': 'fleet'}, inplace=True)
    # df=df.groupby(imo)
    df = df[['attained_rating','fleet','imo']]
    df['attained_rating'] = df['attained_rating'].str[0]
   
    grouped_df = df.groupby(['fleet', 'attained_rating'])['imo'].nunique().reset_index()
    grouped_df.rename(columns={'imo': 'count'}, inplace=True)
    
    # df = df.groupby(['fleet','imo', 'attained_rating']).size().reset_index(name='count')
    grouped_df['fleet']=pd.to_numeric(grouped_df['fleet'])
    grouped_df.sort_values(by='fleet', inplace=True)
    print(grouped_df)
    grouped_df['fleet']='Fleet '+ grouped_df['fleet'].astype(str)
    # result = df.pivot_table(index='fleet', columns='attained_rating', values='count', fill_value=0).reset_index()
    # # Convert the result to the desired format
    # final_result = []
    # for index, row in sorted(result.iterrows(), key=lambda x: int(x[1]['fleet'])):
    #     fleet_dict = {'fleet': str(row['fleet'])}
    #     for col in result.columns[1:]:
    #         fleet_dict[col] = int(row[col])
    #     final_result.append(fleet_dict)\
    json_string = grouped_df.to_json(orient='records')
    json_string = json.loads(json_string)

    return json_string

@router.get('/api/v1/cii/cii_all_fleet')
async def index(db: AsyncSession = Depends(get_db_async),vdm_db: AsyncSession = Depends(get_vdm_db_async)):
    data = await utility.get_data_async(key=CACHEKEY.FINAL_RESULT_CIIALLFLEET)
    cache = False
    if data is not None:

        cache = True
        print("from cache")
    else:
        data =  await cii_all_fleet_cal(db,vdm_db)
        
        try:
                if data is not None:
                    cache = False
                    data = json.dumps(jsonable_encoder(data))
                    state = await utility.set_data_async(key=CACHEKEY.FINAL_RESULT_CIIALLFLEET, value= data,seconds=604800)
                    
                
                    if state is True:
                            print('Cache Set Successfully') 

        except Exception as e:
                print(e)
                print('cache set failure')

    data = json.loads(data)

    return data
    
    

@router.get('/api/v2/cii/yearly_data')
async def index(db: AsyncSession = Depends(get_db_async),vdm_db: AsyncSession = Depends(get_vdm_db_async),token : AsyncSession = Depends(get_token_async)):
    print("start yearly_data..........")
    # username = token['username']
    # user_vessels = await cache_set.get_user_vessel(db)
    # if user_vessels:
    #     user_vessels = list((user_vessels[0]['imo']).split(","))
    attributes_id = [4,8,61]
    vessel = await cache_set.get_all_vdm_vessel_attribute(vdm_db)
    vessel = list(filter(lambda x:x['attribute_id'] in attributes_id, vessel))
    
    vessel_list = list(filter(lambda x:x['attribute_id'] == 4 , vessel))
    
    vessel_list = [i['imo'] for i in vessel_list]
    mcr_data = vessel
    data_dict = {item['imo']: {'dwt': '', 'ship_type': '', 'ship_name': ''} for item in mcr_data}
    
    for item in mcr_data:
        
        data_dict[item['imo']][{8: 'dwt', 4: 'ship_type', 61: 'ship_name'}.get(item['attribute_id'])] = item['value']
        

    
    data2 = []
    # print(mcr_data)
    for i , j in data_dict.items():
        # print("i:",i,"j:",j)
        vessel_data_dict = {}
        vessel_data_dict['imo'] = i
        vessel_data_dict['fleet'] = list(filter(lambda x : x['imo'] == i , mcr_data))[0]['fleet_id']
        vessel_data_dict['dwt'] = j['dwt']
        if j['ship_type'] == '1':
            vessel_data_dict['type'] = 'Container'
        elif j['ship_type'] == '2':
            vessel_data_dict['type'] = 'Bulk Carrier'
        elif j['ship_type'] == '5':
            vessel_data_dict['type'] = 'ROPAX' 
        elif j['ship_type'] == '4':
            vessel_data_dict['type'] = 'PAX' 
        elif j['ship_type'] == '3':
            vessel_data_dict['type'] = 'PCTC'
        elif j['ship_type'] == '6':
            vessel_data_dict['type'] = 'TUG'                    
        vessel_data_dict['name'] = j['ship_name']
     
        
        data2.append(vessel_data_dict)
        
    # return data2
        
    # data2 = [{'imo': imo,'fleet':values['fleet_id'], 'dwt': values['dwt'], 'type': values['ship_type'], 'name': values['ship_name']} for imo, values in data_dict.items()]
    # print(mcr_data)
    print("data is passing")
    # print("list",vessel_list)
    # return data2
    year = "2022"
    fleet = "All"
    
    data = await cache_set.get_data_for_cii(db , vessel_list,str(year),fleet)
    if not data: 
        return{"data": []}
    print("data is ready ")
    df=pd.DataFrame.from_dict(data)   
    df_data=pd.DataFrame.from_dict(data2)
    df = df.merge(df_data, on='imo', how='left')
    data_sort=df.sort_values(by="report_date_time")
    data_sort['datetime'] = pd.to_datetime(data_sort['report_date_time'],format='%Y-%m-%dT%H:%M:%S%z')
    data_sort['Month_name'] = data_sort['datetime'].dt.strftime('%B')
    data_sort['Month'] = data_sort['datetime'].dt.strftime('%b')
    data_sort['Year'] = data_sort['datetime'].dt.strftime('%Y')
    data_sort['Date'] = data_sort['datetime'].dt.strftime('%d')

    #Total HS,LS,MGO and Total Fuel
    convert_dict = {
                'fuel_me_rsdl_hs': float,
                'fuel_aux_rsdl_hs': float,
                'fuel_boiler_rsdl_hs': float,
                
                'fuel_me_rsdl_vls': float,
                'fuel_me_rsdl_uls': float,
                'fuel_aux_rsdl_vls': float,
                'fuel_aux_rsdl_uls':float,
                'fuel_boiler_rsdl_vls':float,
                'fuel_boiler_rsdl_uls':float,
                
                'fuel_me_dstlt_vls':float,
                'fuel_me_dstlt_uls':float,
                'fuel_me_tnktnr_dstlt_vls':float,
                'fuel_aux_dstlt_vls':float,
                'fuel_aux_dstlt_uls':float,
                'fuel_aux_tnktnr_dstlt_vls':float,
                'fuel_boiler_dstlt_vls':float,
                'fuel_boiler_dstlt_uls':float,
                
                'fuel_boiler_tnktnr_dstlt_vls':float,
                "miles_by_gps":float
                
                
                }
    data_sort = data_sort.astype(convert_dict)
    data_sort['Total_Calculated_HS']= data_sort[['fuel_me_rsdl_hs',"fuel_aux_rsdl_hs",'fuel_boiler_rsdl_hs']].sum(axis=1)
    data_sort['Total_Calculated_LS'] = data_sort[['fuel_me_rsdl_vls','fuel_me_rsdl_uls','fuel_aux_rsdl_vls','fuel_aux_rsdl_uls', 'fuel_boiler_rsdl_vls','fuel_boiler_rsdl_uls']].sum(axis=1)
    data_sort['Total_Calculated_ULS'] = data_sort[['fuel_me_dstlt_vls','fuel_me_dstlt_uls','fuel_me_tnktnr_dstlt_vls','fuel_aux_dstlt_vls','fuel_aux_dstlt_uls','fuel_aux_tnktnr_dstlt_vls','fuel_boiler_dstlt_vls','fuel_boiler_dstlt_uls','fuel_boiler_tnktnr_dstlt_vls']].sum(axis=1)
    data_sort['Total_Calculated_Fuel'] = data_sort[['Total_Calculated_HS' ,'Total_Calculated_LS' , 'Total_Calculated_ULS']].sum(axis=1)
    #HS_CO2,LSCO2,MGO_CO2 and Total CO2
    data_sort['HS_CO2'] = 3.114 * data_sort["Total_Calculated_HS"]
    data_sort['LS_CO2'] = 3.151 * data_sort["Total_Calculated_LS"]
    data_sort['ULS_CO2'] = 3.206 * data_sort["Total_Calculated_ULS"]
    data_sort['Total_CO2'] = data_sort[['HS_CO2' ,'LS_CO2' ,'ULS_CO2']].sum(axis=1) 
    data_sort['Total_CO2'] = data_sort['Total_CO2'].astype(float) 

    data_sort=data_sort[['datetime', 'imo','fleet','name', 'Month', 'Year', 'Month_name','Total_CO2',"miles_by_gps" , "dwt" , "type"]]
    
    data_sort= data_sort.fillna(0)
    data_sort = data_sort.replace("", 0)
    data_sort= data_sort[data_sort['dwt'] != 0.0]
    
    data_sort['dwt'] = data_sort['dwt'].astype(float)
    Noon_gp= data_sort.groupby(['imo','name','type','Year','fleet']).agg({"Total_CO2":"sum","miles_by_gps":"sum","dwt":"mean"}).reset_index()
    
    Noon_gp["Attained_CII"]=((Noon_gp["Total_CO2"]*(10**6))/(Noon_gp["miles_by_gps"]*Noon_gp["dwt"])).round(2)
    # Noon_gp = Noon_gp.to_json(orient = 'records')
    # dict_Bulker_Tanker = json.loads(Noon_gp)
    # return dict_Bulker_Tanker
    # Noon_Tanker=Noon_gp[Noon_gp["type"]=="Tanker"]
    # Noon_container = Noon_gp[Noon_gp["type"]=="1"]
    # Noon_Bulker = Noon_gp[Noon_gp["type"]=="2"]
    # Noon_PCTC = Noon_gp[Noon_gp["type"]=="3"]
    # Noon_Ropax = Noon_gp[Noon_gp["type"]=="5"]
    
    
    if not Noon_gp.empty:
        def rqrd_cii(x,y,z):
            
            if y=='1':
                return (1984*(x)**-0.489)
            elif y=='2':
                if (x>=279000):
                    return (4745*(279000)**-0.622)
                else:
                    return (4745*(x)**-0.622)
            elif y=='5':
                return (7540*(x)**-0.587)
            else:#roro cargo ship(vehicle carrier)
                return (5739*(x)**-0.631)
    
        Noon_gp['Required_CII'] = Noon_gp.apply(lambda x: rqrd_cii(x['dwt'], x["type"],x['imo']), axis=1)
        Noon_gp["Required_CII_percent_2022"] = Noon_gp["Required_CII"]*(3/100)
        Noon_gp["Required_CII_2022"] = Noon_gp["Required_CII"]-Noon_gp["Required_CII_percent_2022"]
        Noon_gp["A/R_2022"]=Noon_gp["Attained_CII"]/Noon_gp["Required_CII_2022"]
        Noon_gp=Noon_gp.round({"A/R_2022":2})
        

        def rating(y,z):
            if z=='1':
                if y>=0 and y<=0.83:
                    return "A"
                elif y>0.83 and y<=0.94:
                    return "B"
                elif y>0.94 and y<=1.07:
                    return "C"
                elif y>1.07 and y<=1.19:
                    return "D"
                elif y == np.inf:
                    return None
                elif y>1.19:
                    return "E"
                else:
                    return " "
            elif z=='5':
                if y>=0 and y<=0.72:
                    return "A"
                elif y>0.72 and y<=0.90:
                    return "B"
                elif y>0.90 and y<=1.12:
                    return "C"
                elif y>1.12 and y<=1.41:
                    return "D"
                elif y == np.inf:
                    return None
                elif y>1.41:
                    return "E"
                else:
                    return " "
            elif z=='2':
                if y>=0 and y<=0.86:
                    return "A"
                elif y>0.86 and y<=0.94:
                    return "B"
                elif y>0.94 and y<=1.06:
                    return "C"
                elif y>1.06 and y<=1.18:
                    return "D"
                elif y == np.inf:
                    return None
                elif y>1.18:
                    return "E"
                else:
                    return " "
            else: 
                if y>=0 and y<=0.86:
                    return "A"
                elif y>0.86 and y<=0.94:
                    return "B"
                elif y>0.94 and y<=1.06:
                    return "C"
                elif y>1.06 and y<=1.16:
                    return "D"
                elif y == np.inf:
                    return None
                elif y>1.19:
                    return "E"
                else:
                    return " "
        
        Noon_gp['Rating_2022'] = Noon_gp.apply(lambda x: rating(x['A/R_2022'],x["type"]), axis=1)
        
      
       
    

    
    

    
    # if not Noon_Tanker.empty:
    #     Noon_Tanker["Required_CII"]=((5247*(Noon_Tanker["dwt"]**-0.610))*0.97)
    #     Noon_Tanker["A/R_2022"]=Noon_Tanker["Attained_CII"]/Noon_Tanker["Required_CII"]
    #     Noon_Tanker=Noon_Tanker.round({"A/R_2022":2})

    #     def Tanker_rating(y):
    #         if y>=0 and y<=0.82:
    #             return "A"
    #         elif y>0.82 and y<=0.93:
    #             return "B"
    #         elif y>0.93 and y<=1.08:
    #             return "C"
    #         elif y>1.08 and y<=1.28:
    #             return "D"
    #         else:
    #             return "E"
    #     Noon_Tanker['Rating_2022'] = Noon_Tanker.apply(lambda x: Tanker_rating(x['A/R_2022']), axis=1)


    

    
    Noon_gp=Noon_gp[["name", 'fleet','imo', 'Year',"A/R_2022","Rating_2022","dwt",
                                        'miles_by_gps','Total_CO2','Required_CII','Attained_CII','type']]

    Noon_gp=Noon_gp.rename({"Total_CO2":"total_co_2","dwt":"deadweight","Required_CII":"required_cii",
                                          "Rating_2022":"attained_rating","miles_by_gps":"sailed_distance",
                                          "type":"vessel_type","Attained_CII":"attained_cii","Year":"year",
                                          "A/R_2022":"a_r","Fleet":"fleet" , "name":"vessel_name"},axis=1)

                                          
    Noon_gp=Noon_gp[["total_co_2","deadweight","vessel_name","required_cii","attained_rating",
                                    "sailed_distance","vessel_type","imo","attained_cii","year","a_r","fleet"]]
    Noon_gp=Noon_gp.round(2)
    
    Noon_gp["year"]=Noon_gp["year"].astype(int)
    # Noon_gp['fleet'] = "Fleet "+ Noon_gp["fleet"]

    Noon_gp = Noon_gp.to_json(orient = 'records')
    dict_Bulker_Tanker = json.loads(Noon_gp)
    # return dict_Bulker_Tanker
    data_dict = []

    for i in dict_Bulker_Tanker:
        i['attained_rating'] = list(i['attained_rating'])
        i['fleet'] = "Fleet "+ str(i["fleet"])
        
        data_dict.append(i)

    return data_dict
    
@router.get('/api/v1/key_date/{imo}',status_code=200)
async def index(imo:str,db : AsyncSession = Depends(get_db_async),token : AsyncSession = Depends(get_token_async)):
    data = await cache_set.get_key_date(db,None)
    data = list(filter(lambda x:x['imo'] == imo , data))
    if not data:
        return []
    key_df = pd.DataFrame(data)
    key_df['date'] = pd.to_datetime(key_df['date'],format="%Y-%m-%dT%H:%M:%S").dt.strftime('%d-%b-%Y')
    out_data = key_df.to_json(orient="records")
    out_data = json.loads(out_data)
    return out_data

@router.get('/api/v1/key_date/multi/{imo}',status_code=200)
async def key_dates(imo:str,db : AsyncSession = Depends(get_db_async),v_db : AsyncSession = Depends(get_vdm_db_async)):
    imo_list = imo.split(',')
    mcr_data = await cache_set.get_all_vdm_vessel_attribute(v_db)
    mcr_data = list(filter(lambda x:x['imo'] in imo_list , mcr_data))
    if not mcr_data:
        return {'data':[]}
    mdf = pd.DataFrame(mcr_data)
    vessel_dict = pd.Series(mdf['name'].values,index=mdf['imo']).to_dict()
    data = await cache_set.get_key_date(db,None)
    data = list(filter(lambda x:x['imo'] in imo_list , data))


    if not data:
        return {'data':[]}
    key_df = pd.DataFrame(data)
    key_df = key_df.sort_values(by=['imo'])
    key_df['group'] = key_df.groupby('imo').ngroup()
    key_df['date'] = pd.to_datetime(key_df['date'],format="%Y-%m-%dT%H:%M:%S").dt.strftime('%d %b %Y')
   
    # key_df['date'] = pd.to_datetime(key_df['date'],format="%Y-%m-%dT%H:%M:%S").dt.strftime('%d-%b-%Y')
    key_df['end_dd_date'] = pd.to_datetime(key_df['end_dd_date'],format="%Y-%m-%dT%H:%M:%S").dt.strftime('%d-%b-%Y')
    key_df['end_date'] = key_df['end_dd_date'].fillna(key_df['date'])
    key_df['start_date'] = key_df['date']
    key_df['label']='From ' + key_df['start_date'] + ' To ' + key_df['end_date']+"_"+ key_df['description'] + '('+ key_df['imo']+')'
    key_df['date'] = key_df['end_dd_date'].fillna(key_df['date'])
    key_df['intervention']=key_df['date']+key_df['description']
    key_df['vessel_name'] = np.nan
    key_df['vessel_name'] = key_df['vessel_name'].fillna(key_df['imo'].apply(lambda x: vessel_dict.get(x)))
    out_data = key_df.to_json(orient="records")
    out_data = json.loads(out_data)
    return out_data

@router.get('/api/v2/key_date/multi/{imo}',status_code=200)
async def index(imo:str,db : AsyncSession = Depends(get_db_async),v_db : AsyncSession = Depends(get_vdm_db_async),token : AsyncSession = Depends(get_token_async)):
    api_max=await querydata.get_noondata_latest(db,imo)
    if not api_max:
        return []
    #data = json.dumps(jsonable_encoder(api_max))
    #noondata_max = json.loads(data)
    noondata_min_data = await utility.get_data_async(key=CACHEKEY.NOONDATAMIN+imo)
    cache = False
    if noondata_min_data is not None:
        noondata_min_data = json.loads(noondata_min_data)
        cache = True
    else:
        try:
            noondata_min_data=[]
            api_min=await querydata.get_noondata_old(db,imo)
            noondata_min = json.dumps(jsonable_encoder(api_min))
            noondata_min = json.loads(noondata_min)
            if noondata_min is not None:
                noondata_min_data.append(noondata_min)
                cache = False
                state = await utility.set_data_async(key=CACHEKEY.NOONDATAMIN+imo, value=json.dumps(noondata_min_data),seconds=31536000)
                #print(state)
                if state is True:
                    print('Cache Set Successfully')
        except:
            print('cache set failure')


    imo_list = imo.split(',')
    mcr_data = await cache_set.get_all_vdm_vessel_attribute(v_db)
    mcr_data = list(filter(lambda x:x['imo'] in imo_list and x['attribute_id'] == 148 , mcr_data))
    
    mdf = pd.DataFrame(mcr_data)
    vessel_dict = pd.Series(mdf['name'].values,index=mdf['imo']).to_dict()
    print('********6',noondata_min_data,api_max)
    data = await cache_set.get_keydates_by_noondata(db,imo_list,noondata_min_data[0],api_max)
    # data = list(filter(lambda x:x['imo'] in imo_list , data))
    #print('********7')
    if not data:
        return []
    key_df = pd.DataFrame(data)
    key_df = key_df.sort_values(by=['imo'])
    key_df['group'] = key_df.groupby('imo').ngroup()

    key_df['date'] = pd.to_datetime(key_df['date'],format="%Y-%m-%dT%H:%M:%S").dt.strftime('%d-%b-%Y')
    key_df['end_dd_date'] = pd.to_datetime(key_df['end_dd_date'],format="%Y-%m-%dT%H:%M:%S").dt.strftime('%d-%b-%Y')

    key_df['end_date'] = key_df['end_dd_date'].fillna(key_df['date'])
    key_df['start_date'] = key_df['date']
    key_df['date'] = key_df['end_dd_date'].fillna(key_df['date'])
    key_df = key_df.rename(columns={'intervention': 'intervention_value'})
    key_df['intervention_value']=key_df['intervention_value'].str.replace('+', '%2B')
    key_df['intervention']=key_df['date']+'_'+key_df['description']
    key_df['vessel_name'] = np.nan
    key_df['vessel_name'] = key_df['vessel_name'].fillna(key_df['imo'].apply(lambda x: vessel_dict.get(x)))
    key_df['label']='From ' + key_df['start_date'] + ' To ' + key_df['end_date']+ key_df['description'] + '('+ key_df['imo']+')'
    out_data = key_df.to_json(orient="records")
    out_data = json.loads(out_data)
    return out_data



@router.get('/api/v1/cii/dashboard/weekly/{imo}')
async def get_cii(imo:str,db : AsyncSession = Depends(get_db_async),vdm_db:AsyncSession = Depends(get_vdm_db_async),token : AsyncSession = Depends(get_token_async)):
    cii_weekly = await cache_set.get_cii_weekly(db,imo)
    vdm_vessel_data = await cache_set.get_all_vdm_vessel_attribute(vdm_db)
    
    total=0
    sailed_dist=0
    dwt = list(filter(lambda x:x['imo'] == imo and x['attribute_id'] == 8 , vdm_vessel_data))[0]['value']
    dwt=float(dwt)

    for cii in cii_weekly:
        cii1 = []
        cii1.append(cii['attained_rating'])
        cii['attained_rating_table'] = cii1
        cii['attained_rating'] = cii['attained_rating']
        total=total+float(cii["total_co2"])
        sailed_dist=sailed_dist+float(cii["sailed_distance"])
        a=(float(total)*10**6)
        b=(dwt*float(sailed_dist))
        try:
            cii["actual_cii"]=round(a/b,2)
        except:
            cii["actual_cii"]=0
        if cii['attained_rating'] == 'A':
            cii["color"] = "darkgreen"
        elif cii['attained_rating'] == 'B':
            cii["color"] = "lightgreen"  
        elif cii['attained_rating'] == 'C':
            cii["color"] = "#fadb14"
        elif cii['attained_rating'] == 'D':
            cii["color"] = "#fa8c16"
        elif cii['attained_rating'] == 'E':
            cii["color"] = "#ff4d4f"
    return cii_weekly




@router.get('/api/v1/vessel_daily_data/{imo}',status_code=200)    
async def index(imo:str,db : AsyncSession = Depends(get_db_async),vdm_db:AsyncSession = Depends(get_vdm_db_async),token : AsyncSession = Depends(get_token_async)):
    latest_date = await cache_set.get_latest_date(db,imo)


    if not latest_date:
        return []
    vdm_vessel_data = await cache_set.get_all_vdm_vessel_attribute(vdm_db )
    
    vdm_vessel_data = list(filter(lambda x:x['imo'] == imo and x['attribute_id'] == 4, vdm_vessel_data))

    fleet = vdm_vessel_data[0]['fleet_name']

    ship_type = list(filter(lambda x:x['attribute_id'] == 4 , vdm_vessel_data))[0]['value']

    if ship_type == '1':

       ship_type = 'Container'

    elif ship_type == '2':

       ship_type= 'Bulk carrier'

    elif ship_type == '3':

        ship_type = 'PCTC'

    elif ship_type == '4':

        ship_type = 'PAX'

    elif ship_type == '5':

        ship_type = 'ROPAX'

    elif ship_type == '6':

        ship_type = 'TUG'


    latest_data = await cache_set.get_latest_vessel_location(db,imo,latest_date)


    mydf = latest_data[0]

    new = []

    mydict = {}
    mydict['key'] = str(1)        
    mydict['item_name'] = 'Vessel Name'
    mydict['value']   = mydf['vessel']
    new.append(mydict)

    mydict = {}
    mydict['key'] = str(2)        
    mydict['item_name'] = 'Vessel Type'
    mydict['value']   =  ship_type
    new.append(mydict)



    mydict = {}
    mydict['key'] = str(3)        
    mydict['item_name'] = 'Fleet'
    mydict['value']   =  fleet
    new.append(mydict)



    mydict = {}
    mydict['key'] = str(4)        
    mydict['item_name'] = 'Vessel ID'
    mydict['value']   =  mydf['id_vessel']
    new.append(mydict)



    mydict = {}
    mydict['key'] = str(5)        
    mydict['item_name'] = 'Voyage name'
    if mydf['voyage_code'] != 'nan':
        mydict['value']   =  mydf['voyage_code']
    else:
        mydict['value']   = None
    new.append(mydict)

    mydict = {}

    mydict['key'] = str(6)        

    mydict['item_name'] = 'Voyage Condition'

    mydict['value']   =  mydf['voy_condition']

    new.append(mydict)

    mydict = {}

    mydict['key'] = str(7)        

    mydict['item_name'] = 'Voyage No'

    mydict['value']   =  mydf['voyage_order']

    new.append(mydict)

    mydict = {}

    mydict['key'] = str(8)        

    mydict['item_name'] = 'Report Type'

    mydict['value']   =  mydf['report_type']

    new.append(mydict)

    mydict = {}

    mydict['key'] = str(9)        

    mydict['item_name'] = 'Vessel Status'

    mydict['value']   =  mydf['status']

    new.append(mydict)

    mydict = {}

    mydict['key'] = str(10)        

    mydict['item_name'] = 'Latitude (deg)'
    try:
        mydict['value']   =  round(float(mydf['latitude']),2) 
    except:
        mydict['value']  = None

    new.append(mydict) 

    mydict = {}

    mydict['key'] = str(35)        

    mydict['item_name'] = 'Longitude (deg)'

    try:
        mydict['value']   =  round(float(mydf['longitude']),2)
    except:
        mydict['value'] = None

    new.append(mydict)

    mydict = {}

    mydict['key'] = str(11)        

    mydict['item_name'] = 'Departure Port'

    mydict['value']   =  mydf['port']

    new.append(mydict)

    mydict = {}

    mydict['key'] = str(12)        

    mydict['item_name'] = 'Arrival Port'

    mydict['value']   =  mydf['eta_port']

    new.append(mydict)

    mydict = {}

    mydict['key'] = str(13)        

    mydict['item_name'] = 'Cargo Total (MT)'

    mydict['value']   =  mydf['cargo_total']

    new.append(mydict)

    mydict = {}

    mydict['key'] = str(14)        

    mydict['item_name'] = 'Ballast Weight (MT)'

    mydict['value']   =  mydf['ballast']

    new.append(mydict)

    mydict = {}

    mydict['key'] = str(15)        

    mydict['item_name'] = 'Miles - GPS (NM)'

    mydict['value']   =  mydf['miles_by_gps']

    new.append(mydict)

    mydict = {}

    mydict['key'] = str(16)        

    mydict['item_name'] = 'Distance to Go (NM)'

    mydict['value']   =  mydf['distance_to_next_pilot']

    new.append(mydict)

    mydict = {}

    mydict['key'] = str(17)        

    mydict['item_name'] = 'Speed Through Water (knot)'

    try:
        mydict['value']   =  round(float(mydf['speed_by_log']),2)
    except: 
        mydict['value'] = None 


    new.append(mydict)

    mydict = {}

    mydict['key'] = str(18)        

    mydict['item_name'] = 'Speed Over Ground (knot)'

    try:
        mydict['value']   = round(float(mydf['speed_by_gps']),2)
    except:
        mydict['value'] = None

    new.append(mydict)

    mydict = {}

    mydict['key'] = str(19)        

    mydict['item_name'] = 'RPM'

    try:
        mydict['value']   =  round(float(mydf['rpm']),2)
    except:
        mydict['value']  = None
    new.append(mydict)



    mydict = {}

    mydict['key'] = str(20)        

    mydict['item_name'] = 'Slip (%)'

    try:
        mydict['value']   =  round(float(mydf['slip']),2)
    except:
        mydict['value']  = None

    new.append(mydict)

    mydict = {}
    mydict['key'] = str(21)        
    mydict['item_name'] = 'Draft (m)'
    try:
        mydict['value']   =  round(float(mydf['draft']),2)
    except:
        mydict['value']  = None

    new.append(mydict)

    mydict = {}
    mydict['key'] = str(22)        
    mydict['item_name'] = 'Displacement (m³)'
    mydict['value']   =  mydf['displacement']
    new.append(mydict)


    mydict = {}
    mydict['key'] = str(23)        
    mydict['item_name'] = 'Course at Sea (deg)'
    mydict['value']   =  mydf['course_at_sea']
    new.append(mydict)

    mydict = {}
    mydict['key'] = str(24)        
    mydict['item_name'] = 'Wind Direction (deg)'
    mydict['value']   =  mydf['wind_direction']
    new.append(mydict)

       

    mydict = {}
    mydict['key'] = str(25)        
    mydict['item_name'] = 'Wind Speed (knot)'
    mydict['value']   =  mydf['wind_speed']
    new.append(mydict)

    mydict = {}
    mydict['key'] = str(26)        
    mydict['item_name'] = 'Sea State'
    mydict['value']   =  mydf['sea_state']
    new.append(mydict)



    # mydict = {}
    # mydict['key'] = str(27)        
    # mydict['item_name'] = 'Wind Force'
    # mydict['value']   =  mydf['sea_state']
    # new.append(mydict)



    mydict = {}
    mydict['key'] = str(28)        
    mydict['item_name'] = 'Current Direction (deg)'
    mydict['value']   =  mydf['sea_direction']
    new.append(mydict)

    # mydict = {}
    # mydict['key'] = str(29)        
    # mydict['item_name'] = 'Current Strength'
    # try:
    #     mydict['value']   =  round(float(mydf['sea_state']),2)
    # except:
    #     mydict['value'] = None
    # new.append(mydict)

    mydict = {}
    mydict['key'] = str(30)        
    mydict['item_name'] = 'Sea Water Temp (°C)'
    mydict['value']   =  mydf['sw_temp']
    new.append(mydict)

    mydict = {}
    mydict['key'] = str(31)        
    mydict['item_name'] = 'Total Steaming Time (Hr)'
    mydict['value']   =  mydf['total_steaming_time']
    new.append(mydict)

    mydict = {}
    mydict['key'] = str(32)        
    mydict['item_name'] = 'Total Fuel Cons (MT)'
    try:
        mydict['value']   =  round(float(mydf['total_fo']),2)
    except:
        mydict['value']  = None

    new.append(mydict)

    mydict = {}
    mydict['key'] = str(33)        
    mydict['item_name'] = 'Total CO2 (MT)'
    try:
        mydict['value']   =  round(float(mydf['total_co2']),2)
    except:
        mydict['value']  = None

    new.append(mydict)

    mydict = {}
    mydict['key'] = str(34)        
    mydict['item_name'] = 'EEOI (gm/(MT*NM))'
    mydict['value']   =  mydf['eeoi']
    new.append(mydict)

    return new


@router.get('/api/v1/dailyconsumption_rob/{imo}',status_code=200)
async def garbage_value(imo:str,db : AsyncSession = Depends(get_db_async),token : AsyncSession = Depends(get_token_async)):
    print("------2659------")
    data = await cache_set.get_daily_consumption_rob(db,imo)
    print(data)
    if not data:
        return {"data": [],"Error":"No Noondata"}

    df = pd.DataFrame(data)
    df[['rob_fuel_hs_fo','quantity','fuel_me_rsdl_hs','fuel_aux_rsdl_hs','fuel_boiler_rsdl_hs','rob_fuel_ls_fo','fuel_me_rsdl_vls','fuel_me_rsdl_uls','fuel_aux_rsdl_vls','fuel_aux_rsdl_uls','fuel_boiler_rsdl_vls','fuel_boiler_rsdl_uls','fuel_me_dstlt_uls','fuel_me_dstlt_vls','fuel_aux_dstlt_uls','fuel_aux_dstlt_vls','fuel_boiler_dstlt_uls','fuel_boiler_dstlt_vls','fuel_boiler_tnktnr_dstlt_vls','cy_lub_oil_received_me_cc','cy_lub_added_to_system_me_cc','cy_lub_oil_received_me_cyl','oil_cyl','cy_lub_oil_received_ae_cc','cy_lub_added_to_system_ae_cc','fuel_me_tnktnr_dstlt_vls','fuel_aux_tnktnr_dstlt_vls','rob_dstlt_uls','rob_dstlt_vls','rob_tnktnr_dstlt_vls']] = df[['rob_fuel_hs_fo','quantity','fuel_me_rsdl_hs','fuel_aux_rsdl_hs','fuel_boiler_rsdl_hs','rob_fuel_ls_fo','fuel_me_rsdl_vls','fuel_me_rsdl_uls','fuel_aux_rsdl_vls','fuel_aux_rsdl_uls','fuel_boiler_rsdl_vls','fuel_boiler_rsdl_uls','fuel_me_dstlt_uls','fuel_me_dstlt_vls','fuel_aux_dstlt_uls','fuel_aux_dstlt_vls','fuel_boiler_dstlt_uls','fuel_boiler_dstlt_vls','fuel_boiler_tnktnr_dstlt_vls','cy_lub_oil_received_me_cc','cy_lub_added_to_system_me_cc','cy_lub_oil_received_me_cyl','oil_cyl','cy_lub_oil_received_ae_cc','cy_lub_added_to_system_ae_cc','fuel_me_tnktnr_dstlt_vls','fuel_aux_tnktnr_dstlt_vls','rob_dstlt_uls','rob_dstlt_vls','rob_tnktnr_dstlt_vls']].apply(pd.to_numeric)
    df = df.fillna(0)
    df = df.sort_values(by='report_date_time', ascending=False).reset_index()
    df['report_date_time'] = pd.to_datetime(df['report_date_time'],format='%Y-%m-%dT%H:%M:%S').dt.strftime('%Y-%m-%d')
    print(df)

    df_grpby = df.groupby(['report_date_time','fuel_type']).agg({'quantity': np.sum,'fuel_me_rsdl_hs': np.sum,'fuel_aux_rsdl_hs': np.sum,'fuel_boiler_rsdl_hs': np.sum,'fuel_me_rsdl_vls': np.sum,'fuel_me_rsdl_uls': np.sum,'fuel_aux_rsdl_vls': np.sum,'fuel_aux_rsdl_uls': np.sum,'fuel_boiler_rsdl_vls': np.sum,'fuel_boiler_rsdl_uls': np.sum,'fuel_me_dstlt_uls': np.sum,'fuel_me_dstlt_vls': np.sum,'fuel_aux_dstlt_uls': np.sum,'fuel_aux_dstlt_vls': np.sum,'fuel_boiler_dstlt_uls': np.sum,'fuel_boiler_dstlt_vls': np.sum,'fuel_boiler_tnktnr_dstlt_vls': np.sum,'cy_lub_oil_received_me_cc': np.sum,'cy_lub_added_to_system_me_cc': np.sum,'cy_lub_oil_received_me_cyl': np.sum,'oil_cyl': np.sum,'cy_lub_oil_received_ae_cc': np.sum,'cy_lub_added_to_system_ae_cc': np.sum,'fuel_me_tnktnr_dstlt_vls': np.sum,'fuel_aux_tnktnr_dstlt_vls':np.sum}).reset_index()
    df_sorted = df_grpby.sort_values(by='report_date_time', ascending=False).reset_index()

    # non_aggregated = non_aggregated.sort_values(by='report_date_time', ascending=False).reset_index()
    # result_df = pd.merge(df_sorted, non_aggregated, on=['report_date_time', 'fuel_type'])
    # result_df = result_df.sort_values(by='report_date_time', ascending=False).reset_index()
    # json_con = df_sorted.to_json(orient="records")
    first_df = df_sorted.head(1)
    second_df = df_sorted.iloc[1:2]
    print(first_df)
    print(second_df)
    # data = json.loads(json_con)

    non_aggregated = df.groupby(['report_date_time', 'fuel_type']).agg({'rob_fuel_hs_fo': 'first','rob_fuel_ls_fo': 'first','rob_dstlt_uls':'first','rob_dstlt_vls':'first','rob_tnktnr_dstlt_vls':'first'}).reset_index()
    non_aggregated = non_aggregated.sort_values(by='report_date_time', ascending=False).reset_index()
    print('im 213478')
    print(non_aggregated)
    result_df1 = pd.merge(first_df, non_aggregated, on=['report_date_time', 'fuel_type'])
    result_df1 = result_df1.sort_values(by='report_date_time', ascending=False).reset_index()
    today_data = result_df1.to_json(orient="records")
    today_data = json.loads(today_data)
    today_data = today_data[0]

    result_df2 = pd.merge(second_df, non_aggregated, on=['report_date_time', 'fuel_type'])
    result_df2 = result_df2.sort_values(by='report_date_time', ascending=False).reset_index()
    print(result_df2)
    previous_data = result_df2.to_json(orient="records")
    previous_data = json.loads(previous_data)
    print('in line 2725')
    print(previous_data)
    previous_data = previous_data[0]

    # if not data:
    #     return []
    # today_data=data[0]
    latest_date1 = data[0]['report_date_time']
    latest_date2 = data[1]['report_date_time']

    print('today_data:',today_data)
    print('previous_data:',previous_data)
    
    # previous_data=data[1]

    # return {'today_data':today_data,'previous_data':previous_data}

    final_data=[]
    my_data = {}
    my_data['key'] = str(1)
    my_data['item_name'] =   "Fuel HS"
    my_data['unit'] =   "MT"

    # my_data['pre_date'] = datetime.strptim_e(previous_data['corrected_date'], '%Y-%m-%dT%H:%M:%S')
    my_data['pre_date'] = datetime.strptime(previous_data['report_date_time'],'%Y-%m-%d').strftime('%d %b %Y')
    # my_data['pre_date']= pd.to_datetime(previous_data['corrected_date'],format='%Y-%m-%dT%H:%M:%S').dt.strftime('%d %b %Y')
    my_data['preROB'] = float( previous_data['rob_fuel_hs_fo'])
    my_data['preROB']= ('{:,}'.format(my_data['preROB']))
    if today_data['fuel_type'] in ['HSFO','HSFO380','HSFO500','HSFO700','RESIDUAL HS']:
        my_data['loaded'] = today_data['quantity']
    else:
        my_data['loaded'] = 0
    my_data['post_date'] = datetime.strptime(today_data['report_date_time'],'%Y-%m-%d').strftime('%d %b %Y')
    my_data['main_engine'] = float(today_data[ "fuel_me_rsdl_hs" ])
    my_data['aux_engine'] =   float(today_data[ "fuel_aux_rsdl_hs" ])
    my_data['boiler'] = float(today_data[ "fuel_boiler_rsdl_hs" ])

    my_data['total'] = round(float(my_data['main_engine']) + float(my_data['aux_engine']) + float(my_data['boiler']),2)

    my_data['rob'] = round(float(today_data['rob_fuel_hs_fo'])  , 2)
    my_data['rob'] = ('{:,}'.format(my_data['rob']))
    final_data.append(my_data)

    my_data = {}
    my_data['key'] = str(2)
    my_data['item_name'] =   "Fuel LS"
    my_data['unit'] =   "MT"

    my_data['preROB'] = float(previous_data['rob_fuel_ls_fo'])
    my_data['preROB']= ('{:,}'.format(my_data['preROB']))

    my_data['main_engine'] = float(today_data[ "fuel_me_rsdl_vls" ]) + float(today_data["fuel_me_rsdl_uls"])
    my_data['aux_engine'] =  float(today_data[ "fuel_aux_rsdl_vls" ]) + float(today_data["fuel_aux_rsdl_uls"])
    my_data['boiler'] = float(today_data[ "fuel_boiler_rsdl_vls" ]) + float(today_data["fuel_boiler_rsdl_uls"])

    my_data['total'] = round(float(my_data['main_engine']) + float(my_data['aux_engine']) + float(my_data['boiler']),2)

    my_data['rob'] =round( float(today_data['rob_fuel_ls_fo']), 2)
    my_data['rob'] = ('{:,}'.format(my_data['rob']))
    if today_data['fuel_type'] in ['DISTILLATE VLS', 'LSFO', 'RESIDUAL VLS', 'TANKTAINER DISTILLATE VLS', 'VLSFO', 'VLSFO380', 'VLSFO500', 'VLSFO700']:
        my_data['loaded'] = today_data['quantity']
    else:
        my_data['loaded'] = 0

    my_data['preROB'] = round(float(my_data['total']) + float(my_data['rob']),2)

    final_data.append(my_data)

    my_data = {}
    my_data['key'] = str(3)
    my_data['item_name'] =   "Fuel ULS"
    my_data['unit'] =   "MT"
    my_data['preROB'] = float(previous_data['rob_dstlt_uls']) + float(previous_data['rob_dstlt_vls']) + float(previous_data['rob_tnktnr_dstlt_vls'])
    my_data['preROB']= ('{:,}'.format(my_data['preROB']))
    my_data['main_engine'] = float(today_data[ "fuel_me_dstlt_uls" ]) + float(today_data["fuel_me_dstlt_vls"]) + float(today_data["fuel_me_tnktnr_dstlt_vls"])
    my_data['aux_engine'] =  float(today_data[ "fuel_aux_dstlt_uls" ]) + float(today_data["fuel_aux_dstlt_vls"]) + float(today_data["fuel_aux_tnktnr_dstlt_vls"])
    my_data['boiler'] = float(today_data[ "fuel_boiler_dstlt_uls" ]) + float(today_data["fuel_boiler_dstlt_vls"]) + float(today_data["fuel_boiler_tnktnr_dstlt_vls"])
    my_data['rob'] =round(float(today_data['rob_dstlt_uls']) + float(today_data['rob_dstlt_vls']) + float(today_data['rob_tnktnr_dstlt_vls']),2)
    my_data['rob'] = ('{:,}'.format(my_data['rob']))
    my_data['total'] = round(float(my_data['main_engine']) + float(my_data['aux_engine']) + float(my_data['boiler']),2)
    if today_data['fuel_type'] in ['DISTILLATE ULS', 'MDO', 'MGO', 'MGO-DMA LS', 'MGO LS', 'RESIDUAL ULS', 'Tanktainer MGO', 'ULSFO']:
        my_data['loaded'] = today_data['quantity']
    else:
        my_data['loaded'] = 0

    my_data['preROB'] = round(float(my_data['total']) + float(my_data['rob']),2)
    final_data.append(my_data)



    my_data = {}
    my_data['key'] = str(4)
    my_data['item_name'] =   "MECC"
    my_data['unit'] =   "Ltr"
    my_data['loaded'] = today_data['cy_lub_oil_received_me_cc']
    my_data['main_engine'] = ""
    my_data['aux_engine'] =  ""
    my_data['boiler'] = ""
    my_data['total'] =    round(float(today_data['cy_lub_added_to_system_me_cc']), 2)

    final_data.append(my_data)



    my_data = {}
    my_data['key'] = str(5)
    my_data['item_name'] =   "MECYL"
    my_data['unit'] =   "Ltr"
    my_data['loaded'] = today_data['cy_lub_oil_received_me_cyl']
    my_data['main_engine'] = ""
    my_data['aux_engine'] =  ""
    my_data['boiler'] = ""
    my_data['total'] =    round((float(today_data['oil_cyl'])), 2)
    final_data.append(my_data)



    my_data = {}
    my_data['key'] = str(6)
    my_data['item_name'] =   "AECC"
    my_data['unit'] =   "Ltr"
    my_data['loaded'] = today_data['cy_lub_oil_received_ae_cc']
    my_data['main_engine'] = ""
    my_data['aux_engine'] =   ""  
    my_data['boiler'] = ""
    my_data['total'] =  round( float(today_data['cy_lub_added_to_system_ae_cc']), 2)

    final_data.append(my_data)

    return final_data






@router.get('/api/v1/cargo/{fleet}')
async def index(fleet:str = None,db: AsyncSession = Depends(get_db_async),vdm_db: AsyncSession = Depends(get_vdm_db_async),token : AsyncSession = Depends(get_token_async)):
    print("stating.....")
    # vessel = await cache_set.get_vdm_vessels(vdm_db,fleet)
    # vessel_list = [i['imo'] for i in vessel]
    
    attributes_id = [4,8]
    
    mcr_data = await cache_set.get_all_vdm_vessel_attribute(vdm_db)
    mcr_data = list(filter(lambda x:x['attribute_id'] in  attributes_id , mcr_data))
    
    if fleet == 'All':
        # mcr_data = await cache_set.get_mcr_filter(vdm_db)
        pass
    else:
        # mcr_data = await cache_set.get_mcr_filter_for_all(vdm_db ,fleet)
        mcr_data = list(filter(lambda x:x['fleet'] == int(fleet) , mcr_data))
    vessel_list_fleet= [i['imo'] for i in mcr_data]
    vessel_list_fleet = set(vessel_list_fleet)
    vessel_list = list(vessel_list_fleet)
    
    
    data_dict = {item['imo']: {'dwt': '', 'ship_type': ''} for item in mcr_data}
    
    for item in mcr_data:
        
        data_dict[item['imo']][{8: 'dwt', 4: 'ship_type'}.get(item['attribute_id'])] = item['value']
        

    
    data2 = []
    vessel_types = await cache_set.get_vessel_types(vdm_db)

    vessel_types = {item['id']: item['name'] for item in vessel_types}

    # print(mcr_data)
    for i , j in data_dict.items():
        # print("i:",i,"j:",j)
        vessel_data_dict = {}
        vessel_data_dict['imo'] = i
        vessel_data_dict['fleet'] = list(filter(lambda x : x['imo'] == i , mcr_data))[0]['fleet_name']
        vessel_data_dict['dwt'] = j['dwt']
        vessel_data_dict['type'] = vessel_types[int(j['ship_type'])]
        # if j['ship_type'] == '1':
        # elif j['ship_type'] == '2':
        #     vessel_data_dict['type'] = 'Bulk Carrier'
        # elif j['ship_type'] == '5':
        #     vessel_data_dict['type'] = 'ROPAX' 
        # elif j['ship_type'] == '4':
        #     vessel_data_dict['type'] = 'PAX' 
        # elif j['ship_type'] == '3':
        #     vessel_data_dict['type'] = 'PCTC'
        # elif j['ship_type'] == '6':
        #     vessel_data_dict['type'] = 'TUG'    
        # elif j['ship_type'] == '7':
        #     vessel_data_dict['type'] = 'RO-RO'                 
        vessel_data_dict['name'] = list(filter(lambda x : x['imo'] == i , mcr_data))[0]['name']
     
        
        data2.append(vessel_data_dict)

    year = str((date.today()).year)
    print("Getting datasss")
    
    data = await cache_set.get_cargo_data(db, year,vessel_list,str(fleet))
    if not data:
        return {"data":[]}
    # return data
    def Cargo_Utilization(data):
        print("inside function")
        df=pd.DataFrame.from_dict(data)
       
        df_data=pd.DataFrame.from_dict(data2)
        # return 0
        df = df.merge(df_data, on='imo', how='left')
       
        
        # df['datetime'] = pd.to_datetime(df['report_date_time'],format='%Y-%m-%dT%H:%M:%S%z')
        # df['Month_name'] = df['datetime'].dt.strftime('%B')
        # df['Month'] = df['datetime'].dt.strftime('%b')
        # df['Year'] = df['datetime'].dt.strftime('%Y')
        # df['Date'] = df['datetime'].dt.strftime('%d')
        
        #Total HS,LS,MGO and Total Fuel
        convert_dict = {
                'fuel_me_rsdl_hs': float,
                'fuel_aux_rsdl_hs': float,
                'fuel_boiler_rsdl_hs': float,
                
                'fuel_me_rsdl_vls': float,
                'fuel_me_rsdl_uls': float,
                'fuel_aux_rsdl_vls': float,
                'fuel_aux_rsdl_uls':float,
                'fuel_boiler_rsdl_vls':float,
                'fuel_boiler_rsdl_uls':float,
                
                'fuel_me_dstlt_vls':float,
                'fuel_me_dstlt_uls':float,
                'fuel_me_tnktnr_dstlt_vls':float,
                'fuel_aux_dstlt_vls':float,
                'fuel_aux_dstlt_uls':float,
                'fuel_aux_tnktnr_dstlt_vls':float,
                'fuel_boiler_dstlt_vls':float,
                'fuel_boiler_dstlt_uls':float,
                'fuel_boiler_tnktnr_dstlt_vls':float,
                
                
                
                }
        df = df.astype(convert_dict)
        df['Total_Calculated_HS']= df[['fuel_me_rsdl_hs',"fuel_aux_rsdl_hs",'fuel_boiler_rsdl_hs']].sum(axis=1)
        df['Total_Calculated_LS'] = df[['fuel_me_rsdl_vls','fuel_me_rsdl_uls','fuel_aux_rsdl_vls','fuel_aux_rsdl_uls', 'fuel_boiler_rsdl_vls','fuel_boiler_rsdl_uls']].sum(axis=1)
        df['Total_Calculated_ULS'] = df[['fuel_me_dstlt_vls','fuel_me_dstlt_uls','fuel_me_tnktnr_dstlt_vls','fuel_aux_dstlt_vls','fuel_aux_dstlt_uls','fuel_aux_tnktnr_dstlt_vls','fuel_boiler_dstlt_vls','fuel_boiler_dstlt_uls','fuel_boiler_tnktnr_dstlt_vls']].sum(axis=1)
        df['Total_Calculated_Fuel'] = df[['Total_Calculated_HS' ,'Total_Calculated_LS' , 'Total_Calculated_ULS']].sum(axis=1)
        
        
        #HS_CO2,LSCO2,MGO_CO2 and Total CO2
        df['HS_CO2'] = 3.114 * df["Total_Calculated_HS"]
        df['LS_CO2'] = 3.151 * df["Total_Calculated_LS"]
        df['ULS_CO2'] = 3.206 * df["Total_Calculated_ULS"]
        df['Total_CO2'] = df[['HS_CO2' ,'LS_CO2' ,'ULS_CO2']].sum(axis=1)
        df=df[["report_date_time", 'imo','name', 'fleet','voyage_order','Total_CO2',"miles_by_gps","cargo_total" , 'dwt' , 'type']]
        
        
        
        df['voyage'] = df.groupby(['imo'])['voyage_order'].transform(lambda v: v.ffill())
        df['voyage'] = df.groupby(['imo'])['voyage_order'].transform(lambda v: v.bfill())
        df_sort_new=df.sort_values(by=["report_date_time"])
        df_sort_1=df_sort_new[["imo","name","fleet","type","voyage","dwt","cargo_total","miles_by_gps"]]#fleet
       
        #Cargo Utilization
        df_sort_1= df_sort_1.fillna(0)
        df_sort_1 = df_sort_1.replace("", 0)
        
       
        df_sort_1["dwt"]=df_sort_1["dwt"].astype(float)
        df_sort_1["miles_by_gps"]=df_sort_1["miles_by_gps"].astype(float)
        df_sort_1["cargo_total"]=df_sort_1["cargo_total"].astype(float)
        
        df_cargo_utilize=df_sort_1.groupby(['imo',"name","type",'voyage','fleet']).agg({'dwt':'mean','miles_by_gps':'sum','cargo_total':'mean'}).reset_index()#fleet
        df_cargo_utilize["Cargo_voyage"]=((df_cargo_utilize["cargo_total"]*df_cargo_utilize["miles_by_gps"])/(df_cargo_utilize["dwt"]))
        df_cargo_utilize_1=df_cargo_utilize.groupby(['imo',"name","type","fleet"]).agg({'dwt':'mean','miles_by_gps':'sum','cargo_total':'sum','Cargo_voyage':'sum'}).reset_index()
        df_cargo_utilize_1["Cargo_utilization"]=((df_cargo_utilize_1["Cargo_voyage"])/(df_cargo_utilize_1["miles_by_gps"]))
        df_cargo_utilize_1["Cargo_utilization"] = df_cargo_utilize_1['Cargo_utilization'].fillna(0)
        df_cargo_utilize_1["Cargo_utilization"] = df_cargo_utilize_1['Cargo_utilization'].replace("", 0)
        df_cargo_utilize_1=df_cargo_utilize_1.round(decimals = 2)
        df_cargo_utilize_1 = df_cargo_utilize_1.rename({"name": 'Vessel Name', "Cargo_utilization": 'Cargo Utilization'}, axis=1)
        df_cargo_utilize_1["Cargo Utilization"]=(100 * df_cargo_utilize_1["Cargo Utilization"]).astype(float)
        
        
        
        #rating
        def Cargo_rating(y):
            if y>60:
                return "A"
            elif y>=50 and y<=60:
                return "B"
            elif y>=40 and y<=50:
                return "C"
            elif y>=30 and y<=40:
                return "D"
            else:
                return "E"
        
        df_cargo_utilize_1['Rating'] = df_cargo_utilize_1.apply(lambda x: Cargo_rating(x['Cargo Utilization']), axis=1)
        
        #rating Color
        def Cargo_rating_color(y):
            if y=="A":
                return "green"
            elif y=="B":
                return "lightgreen"
            elif y=="C":
                return "yellow"
            elif y=="D":
                return "orange"
            elif y=="E":
                return "red"
        
        df_cargo_utilize_1['color'] = df_cargo_utilize_1.apply(lambda x: Cargo_rating_color(x['Rating']), axis=1)
        return df_cargo_utilize_1


    df_cargo_utilize_1=Cargo_Utilization(data)

    df_cargo_utilize_Container=df_cargo_utilize_1[df_cargo_utilize_1["type"]=="Container"]
    df_cargo_utilize_Container=df_cargo_utilize_Container.sort_values(by="Cargo Utilization",ascending=False)
    df_cargo_utilize_Container['rank'] = df_cargo_utilize_Container['Cargo Utilization'].rank(ascending=False,method='first')
    df_cargo_utilize_Container['rank']=df_cargo_utilize_Container['rank'].astype(int)
    df_cargo_utilize_Container=df_cargo_utilize_Container[["Vessel Name","dwt","Cargo Utilization","Rating","color","rank"]]
    cargo_container = df_cargo_utilize_Container.to_json(orient="records")
    cargo_container = json.loads(cargo_container)
    

    df_cargo_utilize_Bulker=df_cargo_utilize_1[df_cargo_utilize_1["type"]=="Bulk Carrier"]
    df_cargo_utilize_Bulker=df_cargo_utilize_Bulker.sort_values(by="Cargo Utilization",ascending=False)
    df_cargo_utilize_Bulker['rank'] = df_cargo_utilize_Bulker['Cargo Utilization'].rank(ascending=False,method='first')
    df_cargo_utilize_Bulker['rank']=df_cargo_utilize_Bulker['rank'].astype(int)
    df_cargo_utilize_Bulker=df_cargo_utilize_Bulker[["Vessel Name","dwt","Cargo Utilization","Rating","color","rank"]]
    cargo_bulker = df_cargo_utilize_Bulker.to_json(orient="records")
    cargo_bulker = json.loads(cargo_bulker)
    
    
    
    df_cargo_utilize_PCTC=df_cargo_utilize_1[df_cargo_utilize_1["type"]=="PCTC"]
    df_cargo_utilize_PCTC=df_cargo_utilize_PCTC.sort_values(by="Cargo Utilization",ascending=False)
    df_cargo_utilize_PCTC['rank'] = df_cargo_utilize_PCTC['Cargo Utilization'].rank(ascending=False,method='first')
    df_cargo_utilize_PCTC['rank']=df_cargo_utilize_PCTC['rank'].astype(int)
    df_cargo_utilize_PCTC=df_cargo_utilize_PCTC[["Vessel Name","dwt","Cargo Utilization","Rating","color","rank"]]
    cargo_pctc = df_cargo_utilize_PCTC.to_json(orient="records")
    cargo_pctc = json.loads(cargo_pctc)
   
    
    
    
    df_cargo_utilize_Ropax=df_cargo_utilize_1[df_cargo_utilize_1["type"]=="ROPAX"]
    df_cargo_utilize_Ropax=df_cargo_utilize_Ropax.sort_values(by="Cargo Utilization",ascending=False)
    df_cargo_utilize_Ropax['rank'] = df_cargo_utilize_Ropax['Cargo Utilization'].rank(ascending=False,method='first')
    df_cargo_utilize_Ropax['rank']=df_cargo_utilize_Ropax['rank'].astype(int)
    df_cargo_utilize_Ropax=df_cargo_utilize_Ropax[["Vessel Name","dwt","Cargo Utilization","Rating","color","rank","fleet"]]
    cargo_ropax = df_cargo_utilize_Ropax.to_json(orient="records")
    cargo_ropax = json.loads(cargo_ropax)
    
    
    df_cargo_utilize_ro_ro=df_cargo_utilize_1[df_cargo_utilize_1["type"]=="Ro-Ro"]
    df_cargo_utilize_ro_ro=df_cargo_utilize_ro_ro.sort_values(by="Cargo Utilization",ascending=False)
    df_cargo_utilize_ro_ro['rank'] = df_cargo_utilize_ro_ro['Cargo Utilization'].rank(ascending=False,method='first')
    df_cargo_utilize_ro_ro['rank']=df_cargo_utilize_ro_ro['rank'].astype(int)
    df_cargo_utilize_ro_ro=df_cargo_utilize_ro_ro[["Vessel Name","dwt","Cargo Utilization","Rating","color","rank","fleet"]]
    cargo_ro_ro = df_cargo_utilize_ro_ro.to_json(orient="records")
    cargo_ro_ro = json.loads(cargo_ro_ro)


    print("finished")
    
    return {
    'data': {
    'cargo_container':cargo_container,
    'cargo_bulker':cargo_bulker,
    'cargo_pctc':cargo_pctc,
    'cargo_ropax':cargo_ropax,
    'cargo_ro_ro':cargo_ro_ro}}
    
    
     
        
@router.get('/api/v1/steamming/{fleet}')
async def index(fleet:str = None,db: AsyncSession = Depends(get_db_async),vdm_db: AsyncSession = Depends(get_vdm_db_async),token : AsyncSession = Depends(get_token_async)):
    # user_vessels = await cache_set.get_user_vessel(db,token['username'])
    print("stating.....")
    # vessel = await cache_set.get_vdm_vessels(vdm_db,fleet)
    
    # vessel_list = [i['imo'] for i in vessel]
    year = str((date.today()).year)
    attributes_id = [4,8]
    
    mcr_data = await cache_set.get_all_vdm_vessel_attribute(vdm_db)
    
    mcr_data = list(filter(lambda x:x['attribute_id'] in  attributes_id , mcr_data))


    # year = "2022"
    if fleet == 'All':
        # mcr_data = await cache_set.get_mcr_filter(vdm_db)
        pass
    else:
        # mcr_data = await cache_set.get_mcr_filter_for_all(vdm_db ,fleet)
        mcr_data = list(filter(lambda x:x['fleet'] == int(fleet) , mcr_data))
        
    vessel_list_fleet= [i['imo'] for i in mcr_data]
    vessel_list_fleet = set(vessel_list_fleet)
    vessel_list = list(vessel_list_fleet)
    # return vessel_list
    data_dict = {item['imo']: {'dwt': '', 'ship_type': '', 'ship_name': ''} for item in mcr_data}
    
    for item in mcr_data:
        
        data_dict[item['imo']][{8: 'dwt', 4: 'ship_type', 61: 'ship_name'}.get(item['attribute_id'])] = item['value']
        

    
    data2 = []
    vessel_types = await cache_set.get_vessel_types(vdm_db)

    vessel_types = {item['id']: item['name'] for item in vessel_types}
    # print(mcr_data)
    for i , j in data_dict.items():
        # print("i:",i,"j:",j)
        vessel_data_dict = {}
        vessel_data_dict['imo'] = i
        vessel_data_dict['fleet'] = list(filter(lambda x : x['imo'] == i , mcr_data))[0]['fleet']
        vessel_data_dict['dwt'] = j['dwt']
        # if j['ship_type'] == '1':
        #     vessel_data_dict['type'] = 'Container'
        # elif j['ship_type'] == '2':
        #     vessel_data_dict['type'] = 'Bulk Carrier'
        # elif j['ship_type'] == '5':
        #     vessel_data_dict['type'] = 'ROPAX' 
        # elif j['ship_type'] == '4':
        #     vessel_data_dict['type'] = 'PAX' 
        # elif j['ship_type'] == '3':
        #     vessel_data_dict['type'] = 'PCTC'
        # elif j['ship_type'] == '6':
        #     vessel_data_dict['type'] = 'TUG'     
        vessel_data_dict['type'] = vessel_types[int(j['ship_type'])]
                       
        vessel_data_dict['name'] = list(filter(lambda x : x['imo'] == i , mcr_data))[0]['name']
     
        
        data2.append(vessel_data_dict)
    if vessel_list:
        data = await cache_set.get_steaming_data_by_user(db, year ,vessel_list,fleet)   
        if not data:
            return {'data': []}
        print("---------------------------------------")
        # return data
    else:
        return {'data': []}

    async def Steaming_percentage(data):
        df=pd.DataFrame.from_dict(data)
        df_data=pd.DataFrame.from_dict(data2)
        df = df.merge(df_data, on='imo', how='left')
        df['Date'] = pd.to_datetime(df['report_date_time']).apply(lambda x:x.strftime("%d"))
        df['Month'] = pd.to_datetime(df['report_date_time']).apply(lambda x:x.strftime("%m"))
        df['Year'] = pd.to_datetime(df['report_date_time']).apply(lambda x:x.strftime("%Y"))
        df['Month_name'] = pd.to_datetime(df['report_date_time']).apply(lambda x:x.strftime("%B"))
        df['date'] = pd.to_datetime(df["report_date_time"]).dt.date
        
        df_sort=df.sort_values(by=["report_date_time"])
        df_sort= df_sort.fillna(0)
        df_sort = df_sort.replace("", 0)
        
        
        
        df_sort["me_fuel_only_steaming_time"]=df_sort["me_fuel_only_steaming_time"].astype(float)
        
        df_1 = df_sort.groupby(['imo','name','fleet','type','Year','Month',"Month_name"])['Date'].nunique().reset_index()
        df_2 = df_1.groupby(['imo','name','fleet','type','Year'])['Date'].sum().reset_index()
        df_2 = df_2.rename({"Date":"Total_Date"},axis=1)
        df_time = df_sort.groupby(['imo','name',"type",'Year','fleet'])['me_fuel_only_steaming_time'].sum().reset_index()
        df_time = df_time.rename({"me_fuel_only_steaming_time":"Total_ME_Steaming_Time"},axis=1)
        df_time["Total_ME_Steaming_Time"] = (df_time["Total_ME_Steaming_Time"]/24).round(0).astype(int)
       
        dict_total_days= pd.Series(df_2['Total_Date'].values,index=df_2['imo']).to_dict()
        df_time['Total_Date'] = np.nan
        df_time['Total_Date'] = df_time['Total_Date'].fillna(df_time['imo'].apply(lambda x: dict_total_days.get(x)))
        df_time['Total_Date']=df_time['Total_Date'].astype(int)
        df_time["Steaming_time"]=((df_time["Total_ME_Steaming_Time"]/df_time['Total_Date'])*100).round(2)
        return df_time


    df_time=await Steaming_percentage(data)
    print("50% complete")
    
    
    df_time_Container=df_time[df_time["type"]=="Container"]
    df_time_Container=df_time_Container.sort_values(by="Steaming_time")
    df_time_Container["Steaming_time_mean"]=df_time_Container["Steaming_time"].mean()
    df_time_Container=df_time_Container[["name","Steaming_time","Steaming_time_mean","fleet"]].round(1)
    df_time_Container = df_time_Container.to_json(orient = 'records')
    df_time_container = json.loads(df_time_Container)

    df_time_Bulker=df_time[df_time["type"]=="Bulk Carrier"]
    df_time_Bulker=df_time_Bulker.sort_values(by="Steaming_time")
    df_time_Bulker["Steaming_time_mean"]=df_time_Bulker["Steaming_time"].mean()
    df_time_Bulker=df_time_Bulker[["name","Steaming_time","Steaming_time_mean","fleet"]].round(1)
    df_time_Bulker = df_time_Bulker.to_json(orient = 'records')
    df_time_bulker = json.loads(df_time_Bulker)



    df_time_pctc=df_time[df_time["type"]=="PCTC"]
    df_time_pctc=df_time_pctc.sort_values(by="Steaming_time")
    df_time_pctc["Steaming_time_mean"]=df_time_pctc["Steaming_time"].mean()
    df_time_pctc=df_time_pctc[["name","Steaming_time","Steaming_time_mean"]].round(1)
    df_time_pctc = df_time_pctc.to_json(orient = 'records')
    df_time_pctc = json.loads(df_time_pctc)




   
    
    df_time_Ropax=df_time[df_time["type"]=="ROPAX"]
    df_time_Ropax=df_time_Ropax.sort_values(by="Steaming_time")
    df_time_Ropax["Steaming_time_mean"]=df_time_Ropax["Steaming_time"].mean()
    df_time_Ropax=df_time_Ropax[["name","Steaming_time","Steaming_time_mean"]].round(1)
    df_time_Ropax = df_time_Ropax.to_json(orient = 'records')
    df_time_Ropax = json.loads(df_time_Ropax)
    # print("ending")
    
    
    df_time_ro_ro=df_time[df_time["type"]=="Ro-Ro"]
    df_time_ro_ro=df_time_ro_ro.sort_values(by="Steaming_time")
    df_time_ro_ro["Steaming_time_mean"]=df_time_ro_ro["Steaming_time"].mean()
    df_time_ro_ro=df_time_ro_ro[["name","Steaming_time","Steaming_time_mean"]].round(1)
    df_time_ro_ro = df_time_ro_ro.to_json(orient = 'records')
    df_time_ro_ro = json.loads(df_time_ro_ro)

    return {
    'data':{
        'df_time_container':df_time_container,
        'df_time_bulker':df_time_bulker,
        'df_time_pctc':df_time_pctc,
        'df_time_Ropax':df_time_Ropax,
        'df_time_ro_ro':df_time_ro_ro,
        }
     }


@router.get('/api/v1/fleet_count')
async def get_cii_rank(db : AsyncSession = Depends(get_db_async),vdm_db : AsyncSession = Depends(get_vdm_db_async)):
    mcr_data = await cache_set.get_mcr_filter(vdm_db)
    teu = list(filter(lambda x: x['attribute_id'] == 22  , mcr_data))
    df=pd.DataFrame(teu)
    df.rename(columns={'value':'teu'}, inplace = True)

    # print(df)
    type = sorted(filter(lambda x: x['attribute_id'] == 4, mcr_data), key=lambda x: x['fleet'], reverse=True)# bug fixed by aswathi 30/10/2023


    type=pd.DataFrame(type)
    merged_df =  pd.merge(df, type[['imo','value']], how='left', left_on= "imo",  right_on = "imo")
    merged_df.rename(columns={'value':'ship'}, inplace = True)
    merged_df.loc[merged_df["ship"] == "1", "ship"] = 'Container'
    merged_df.loc[merged_df["ship"] == "2", "ship"] = 'Bulk Carrier'
    merged_df.loc[merged_df["ship"] == "3", "ship"] = 'PCTC'
    merged_df.loc[merged_df["ship"] == "4", "ship"] = 'PAX'
    merged_df.loc[merged_df["ship"] == "5", "ship"] = 'ROPAX'
    merged_df.loc[merged_df["ship"] == "6", "ship"] = 'TUG'
    merged_df.loc[merged_df["ship"] == "7", "ship"] = 'RO-RO'
    
    # merged_df=merged_df[merged_df['ship']=='1']
    # merged_df['ship']='Container'
    #print(merged_df)
   
    # Create a sample DataFrame with a column containing values
    data = {'Ship Capacity': [500, 1500, 2500, 6000, 9000, 14000, 18000, 22000]}

    # Define the value ranges and corresponding categories
    categories = {
        'Small Feeders': (300, 1000),
        'Feedermax': (1000, 3000),
        'Panamax': (3000, 4500),
        'Suezmax': (4500, 12000),
        'ULCV/ULCS': (12000, 25000)
    }

# Function to categorize values based on the specified categories
    def categorize_ship_capacity(capacity):
        for category, (min_value, max_value) in categories.items():
            if min_value <= capacity <= max_value:
                return category
        return 'New Vessel'

# Apply the categorization function to create a new column
    merged_df['teu'] = merged_df['teu'].replace({"NA":None})


    merged_df['vessel_type'] = pd.to_numeric(merged_df['teu']).apply(categorize_ship_capacity)
    print(merged_df)
    condition = (merged_df['ship'] == 'Container') & (merged_df['vessel_type'].isna())
    print(condition)
    merged_df.loc[condition, 'vessel_type'] = 'New Vessel'
    # merged_df['vessel_type'] = merged_df.apply(lambda row: 'New Vessel' if ((row['ship'] == 'Container') and ( row['teu'] is None)) else None, axis=1)
    print(merged_df)
    # Display the DataFrame
    merged_df_vessel=merged_df.groupby(['fleet','ship'])['imo'].count().reset_index()
    #print(merged_df_vessel)
    # merged_df_vessel['']=merged_df_vessel['ship']
    merged_df_vessel['type']='V type'

    merged_df_vessel.rename(columns={'imo':'vessels'}, inplace = True)
    merged_df_vessel=merged_df_vessel.to_json(orient="records")
    merged_df_vessel=json.loads(merged_df_vessel)
    merged_df=merged_df.groupby(['fleet','vessel_type','ship'])['imo'].count().reset_index()
    merged_df=merged_df[merged_df['ship']=='Container']
    
    
    merged_df['ship']=merged_df['vessel_type']

    merged_df['type']='C type'
    merged_df.rename(columns={'imo':'vessels'}, inplace = True)
    merged_df['fleet']=pd.to_numeric(merged_df['fleet'])
    merged_df = merged_df.sort_values(by='fleet')
    merged_df['fleet']=merged_df['fleet'].astype(str)
    
    merged_df=merged_df[['fleet','ship','type','vessels']].to_json(orient="records")
    merged_df=json.loads(merged_df)
    mer=merged_df+merged_df_vessel

    #print(merged_df_vessel)
    # exit(0)
    # merged =  pd.merge(merged_df, merged_df_vessel, how='left', left_on= ,  right_on = "imo")
    # merged = pd.merge(merged_df, merged_df_vessel, on=['fleet', 'vessel_type', 'ship'], how='left')

    # merged=merged_df_vessel+merged_df
    
    # merged = merged_df.sort_values(by='fleet') 

    # merged_df=merged_df.to_json(orient="records")
    # merged_df=json.loads(merged)
    # merged_df=merged_df[[]]
    # { fleet: '18', ship: '', vessels: 18, vessel_type: 'Container' },
    return mer



@router.get('/api/v1/dashboard/fleetcount')
async def get_cii_rank(db : AsyncSession = Depends(get_db_async),vdm_db : AsyncSession = Depends(get_vdm_db_async)):
    mcr_data = await cache_set.get_mcr_filter(vdm_db)
    teu = list(filter(lambda x: x['attribute_id'] == 22  , mcr_data))
    df=pd.DataFrame(teu)
    df.rename(columns={'value':'teu'}, inplace = True)

    #print(df)
    type = list(filter(lambda x: x['attribute_id'] ==4 , mcr_data))
    type=pd.DataFrame(type)
    merged_df =  pd.merge(df, type[['imo','value']], how='left', left_on= "imo",  right_on = "imo")
    merged_df.rename(columns={'value':'ship'}, inplace = True)
    merged_df.loc[merged_df["ship"] == "1", "ship"] = 'Container'
    merged_df.loc[merged_df["ship"] == "2", "ship"] = 'Bulk Carrier'
    merged_df.loc[merged_df["ship"] == "3", "ship"] = 'PCTC'
    merged_df.loc[merged_df["ship"] == "4", "ship"] = 'PAX'
    merged_df.loc[merged_df["ship"] == "5", "ship"] = 'ROPAX'
    merged_df.loc[merged_df["ship"] == "6", "ship"] = 'TUG'
    # merged_df=merged_df[merged_df['ship']=='1']
    # merged_df['ship']='Container'
    #print(merged_df)
   
    # Create a sample DataFrame with a column containing values
    data = {'Ship Capacity': [500, 1500, 2500, 6000, 9000, 14000, 18000, 22000]}

    # Define the value ranges and corresponding categories
    categories = {
        'Small Feeders': (300, 1000),
        'Feedermax': (1000, 3000),
        'Panamax': (3000, 4500),
        'Suezmax': (4500, 12000),
        'ULCV/ULCS': (12000, 24000)
    }

# Function to categorize values based on the specified categories
    def categorize_ship_capacity(capacity):
        for category, (min_value, max_value) in categories.items():
            if min_value <= capacity <= max_value:
                return category
        return ''

# Apply the categorization function to create a new column
    merged_df['teu'] = merged_df['teu'].replace({"NA":None})

    merged_df['vessel_type'] = pd.to_numeric(merged_df['teu']).apply(categorize_ship_capacity)

    # Display the DataFrame
    merged_df=merged_df.groupby(['fleet','vessel_type','ship'])['imo'].count().reset_index()
    merged_df.rename(columns={'imo':'vessels'}, inplace = True)

    #print(merged_df)
    merged_df=merged_df.to_json(orient="records")
    merged_df=json.loads(merged_df)
    # merged_df=merged_df[[]]
    # { fleet: '18', ship: '', vessels: 18, vessel_type: 'Container' },
    return merged_df



# -----------------stub apis------------------------
@router.get('/api/v1/world_cii_rank_container/{fleet}')
async def get_cii_rank(fleet:str = None,db : AsyncSession = Depends(get_db_async),vdm_db : AsyncSession = Depends(get_vdm_db_async),token : AsyncSession = Depends(get_token_async)):
    mcr_data = await cache_set.get_all_vdm_vessel_attribute(vdm_db)
    if fleet !=  'All':
        mcr_data = list(filter(lambda x:x['fleet'] == int(fleet) , mcr_data))


    vessel_list_fleet= [i['name'] for i in mcr_data]
    
    vessel_list_fleet = set(vessel_list_fleet)
    vessel_list = list(vessel_list_fleet)
    # return vessel_list
    
    async def main(stub_type,vessel_list,year):
        cii = []
        vess_attr_filtered = filter(lambda j: j['vessel_name'] in vessel_list and j['year'] == year, stub_type)
        cii += [{ **j} for j in vess_attr_filtered] 
        return cii
    
    
    #cr = open('stub/world_container_rank_data.json')
    container = await read_file_async('stub/world_container_rank_data.json','r')
    #c_ar = open('stub/world_container_a_r_data.json')
    container_ar = await read_file_async('stub/world_container_a_r_data.json','r')
    distinct_years = list(set([item['year'] for item in container]))
    container_data_list = []
    container_ar_data_list = []
    for i in distinct_years:
        container_list = await main(container,vessel_list,i)
        container_data_list.append({'rank_data_'+str(i) : container_list})
    
        container_ar_list = await main(container_ar,vessel_list,i)
        container_ar_data_list.append({'a_r_data_'+str(i) : container_ar_list})
        
    
    
    return {"data":{"rank_data":container_data_list,
                    "a_r_data":container_ar_data_list           
    }}


@router.get('/api/v1/world_cii_rank_bulker/{fleet}')
async def  get_cii_rank(fleet:str = None,db : AsyncSession = Depends(get_db_async),vdm_db : AsyncSession = Depends(get_vdm_db_async),token : AsyncSession = Depends(get_token_async)):
    mcr_data = await cache_set.get_all_vdm_vessel_attribute(vdm_db)
    if fleet !=  'All':
        mcr_data = list(filter(lambda x:x['fleet'] == int(fleet) , mcr_data))

    # return mcr_data
    vessel_list_fleet= [i['name'] for i in mcr_data]
    
    vessel_list_fleet = set(vessel_list_fleet)
    vessel_list = list(vessel_list_fleet)
    # return vessel_list
    
    def main(stub_type,vessel_list,year ):
        cii = []
        vess_attr_filtered = filter(lambda j: j['vessel_name'] in vessel_list  and j['year'] == year, stub_type)
        cii += [{ **j} for j in vess_attr_filtered] 
        return cii
    
    
    #br = open('stub/world_bulker_rank_data.json')
    bulker = await read_file_async('stub/world_bulker_rank_data.json','r')
    #b_ar = open('stub/world_bulker_a_r_data.json')
    bulker_ar = await read_file_async('stub/world_bulker_a_r_data.json','r')
    
    distinct_years = list(set([item['year'] for item in bulker]))
    
    bulker_data_list = []
    bulker_ar_data_list = []
    for i in distinct_years:
        bulker_list = main(bulker,vessel_list,i)
        bulker_data_list.append({'rank_data_'+str(i) : bulker_list})
        
        bulker_ar_list = main(bulker_ar,vessel_list,i)
        bulker_ar_data_list.append({'a_r_data_'+str(i) : bulker_ar_list})
   
    return {"data":{"bulker_rank_data":bulker_data_list,
                    "bulker_a_r_data":bulker_ar_data_list                  
    }}


@router.get('/api/v1/world_cii_yearly/{fleet}')
async def get_cii_rank(fleet:str = None,db : AsyncSession = Depends(get_db_async),vdm_db : AsyncSession = Depends(get_vdm_db_async),token : AsyncSession = Depends(get_token_async)):
    ai_fleet = "Fleet "+fleet
    mcr_data = await cache_set.get_all_vdm_vessel_attribute(vdm_db)
    if fleet !=  'All':
        mcr_data = list(filter(lambda x:x['fleet'] == int(fleet) , mcr_data))

    # return mcr_data
    vessel_list_fleet= [i['name'] for i in mcr_data]
    vessel_list_fleet = set(vessel_list_fleet)
    vessel_list = list(vessel_list_fleet)
    # return vessel_list
    
    def main(stub_type,vessel_list,fleet):
        cii = []
        vess_attr_filtered = filter(lambda j: j['vessel_name'] in vessel_list, stub_type)
        cii += [{"fleet":ai_fleet,**j} for j in vess_attr_filtered] 
        return cii
    
    
    #yc = open('stub/yearly_cii_data.json')
    yearly = await read_file_async('stub/yearly_cii_data.json','r')
    yearly_cii = main(yearly,vessel_list,ai_fleet)

    return {"data":{"world_cii_yearly":yearly_cii            
    }}

@router.get('/api/v1/world_eeoi_bulker/{fleet}')
async def get_cii_rank(fleet:str = None,db : AsyncSession = Depends(get_db_async),vdm_db : AsyncSession = Depends(get_vdm_db_async),token : AsyncSession = Depends(get_token_async)):
    mcr_data = await cache_set.get_all_vdm_vessel_attribute(vdm_db)
    if fleet !=  'All':
        mcr_data = list(filter(lambda x:x['fleet'] == int(fleet) , mcr_data))

    # return mcr_data
    vessel_list_fleet= [i['name'] for i in mcr_data]
    vessel_list_fleet = set(vessel_list_fleet)
    vessel_list = list(vessel_list_fleet)
    # return vessel_list
    
    def main(stub_type,vessel_list):
        cii = []
        vess_attr_filtered = filter(lambda j: j['vessel_name'] in vessel_list, stub_type)
        cii += [{ **j} for j in vess_attr_filtered] 
        return cii
    
    
    #eeoi = open('stub/eeoi_bulker_data.json')
    eeoi_bulker = await read_file_async('stub/eeoi_bulker_data.json','r')
    eeoi_bulker = main(eeoi_bulker,vessel_list)

    return {"data":{"world_eeoi_bulker":eeoi_bulker            
    }}

@router.get('/api/v1/world_eeoi_container/{fleet}')
async def get_cii_rank(fleet:str = None,db : AsyncSession = Depends(get_db_async),vdm_db : AsyncSession = Depends(get_vdm_db_async),token : AsyncSession = Depends(get_token_async)):

    mcr_data = await cache_set.get_all_vdm_vessel_attribute(vdm_db)
    if fleet !=  'All':
        mcr_data = list(filter(lambda x:x['fleet'] == int(fleet) , mcr_data))
    
    if not mcr_data:
        return []
    
    
    vessel_imo_fleet = [i['imo'] for i in mcr_data]
    imo_list = list(set(vessel_imo_fleet))
    current_year = datetime.now().year
    # exit(0)
    print("Here")
    noondata = await cache_set.get_NoonDatas_list(db,imo_list,current_year,current_year,fleet)
    print("Noondata completed")

    # return noondata
    noondata = pd.DataFrame(noondata)
    if noondata.empty:
        return []
    
    noondata.drop_duplicates(subset='gid', keep='first')
    dead_weight = list(filter(lambda x: x['attribute_id'] == 8 , mcr_data))
    vsl_type = list(filter(lambda x: x['attribute_id'] == 4 , mcr_data))
    gross_ton = list(filter(lambda x: x['attribute_id'] == 83 , mcr_data))
    # data = pd.DataFramenoondata()
    noondata[['fuel_me_rsdl_hs','fuel_aux_rsdl_hs','fuel_boiler_rsdl_hs','fuel_me_rsdl_vls','fuel_aux_rsdl_vls','fuel_boiler_rsdl_vls','fuel_me_rsdl_uls','fuel_aux_rsdl_uls','fuel_boiler_rsdl_uls','fuel_me_dstlt_vls','fuel_aux_dstlt_vls','fuel_boiler_dstlt_vls','fuel_me_dstlt_uls','fuel_aux_dstlt_uls','fuel_boiler_dstlt_uls','fuel_me_tnktnr_dstlt_vls','fuel_aux_tnktnr_dstlt_vls','fuel_boiler_tnktnr_dstlt_vls']]=noondata[['fuel_me_rsdl_hs','fuel_aux_rsdl_hs','fuel_boiler_rsdl_hs','fuel_me_rsdl_vls','fuel_aux_rsdl_vls','fuel_boiler_rsdl_vls','fuel_me_rsdl_uls','fuel_aux_rsdl_uls','fuel_boiler_rsdl_uls','fuel_me_dstlt_vls','fuel_aux_dstlt_vls','fuel_boiler_dstlt_vls','fuel_me_dstlt_uls','fuel_aux_dstlt_uls','fuel_boiler_dstlt_uls','fuel_me_tnktnr_dstlt_vls','fuel_aux_tnktnr_dstlt_vls','fuel_boiler_tnktnr_dstlt_vls']].apply(pd.to_numeric)
    noondata=noondata.replace({np.nan:0})
    noondata['totalco2']=((pd.to_numeric(noondata['fuel_me_rsdl_hs'])+pd.to_numeric(noondata['fuel_aux_rsdl_hs'])+pd.to_numeric
    (noondata['fuel_boiler_rsdl_hs']))*3.114)+((pd.to_numeric(noondata['fuel_me_rsdl_vls'])+pd.to_numeric(noondata['fuel_aux_rsdl_vls'])+pd.to_numeric(noondata['fuel_boiler_rsdl_vls'])+pd.to_numeric(noondata['fuel_me_rsdl_uls'])+pd.to_numeric(noondata['fuel_aux_rsdl_uls'])+pd.to_numeric(noondata['fuel_boiler_rsdl_uls']))*3.151)   +((pd.to_numeric(noondata['fuel_me_dstlt_vls'])+pd.to_numeric(noondata['fuel_aux_dstlt_vls'])+pd.to_numeric(noondata['fuel_boiler_dstlt_vls'])+pd.to_numeric(noondata['fuel_me_dstlt_uls'])+pd.to_numeric(noondata['fuel_aux_dstlt_uls'])+pd.to_numeric(noondata['fuel_boiler_dstlt_uls'])+pd.to_numeric(noondata['fuel_me_tnktnr_dstlt_vls'])+pd.to_numeric(noondata['fuel_aux_tnktnr_dstlt_vls'])+pd.to_numeric(noondata['fuel_boiler_tnktnr_dstlt_vls']))*3.206)
    deadweight = pd.DataFrame(dead_weight)
    gross_tonnage = pd.DataFrame(gross_ton)
    vessel_type = pd.DataFrame(vsl_type)
    vessel_type.loc[vessel_type["value"] == "1", "vessel_type"] = 'Container'
    vessel_type.loc[vessel_type["value"] == "2", "vessel_type"] = 'Bulk Carrier'
    vessel_type.loc[vessel_type["value"] == "3", "vessel_type"] = 'PCTC'
    vessel_type.loc[vessel_type["value"] == "4", "vessel_type"] = 'PAX'
    vessel_type.loc[vessel_type["value"] == "5", "vessel_type"] = 'ROPAX'
    vessel_type.loc[vessel_type["value"] == "6", "vessel_type"] = 'TUG'
    vessel_type.loc[vessel_type["value"] == "7", "vessel_type"] = 'Ro-Ro'
    # exit(0)
    noondata['totalco2']=pd.to_numeric(noondata['totalco2'])
    noondata['miles_by_gps']=pd.to_numeric(noondata['miles_by_gps'])
    noondata['cargo_total']=pd.to_numeric(noondata['cargo_total'])
    hfo_columns = ['fuel_me_rsdl_hs', 'fuel_aux_rsdl_hs', 'fuel_boiler_rsdl_hs']
    lfo_columns = ['fuel_me_rsdl_vls', 'fuel_aux_rsdl_vls', 'fuel_boiler_rsdl_vls',
                'fuel_me_rsdl_uls', 'fuel_aux_rsdl_uls', 'fuel_boiler_rsdl_uls']
    mdo_mgo_columns = ['fuel_me_dstlt_vls', 'fuel_aux_dstlt_vls', 'fuel_boiler_dstlt_vls',
                    'fuel_me_dstlt_uls', 'fuel_aux_dstlt_uls', 'fuel_boiler_dstlt_uls',
                    'fuel_me_tnktnr_dstlt_vls', 'fuel_aux_tnktnr_dstlt_vls', 'fuel_boiler_tnktnr_dstlt_vls']
    
    
# Sum the respective columns for each fuel type
    noondata['HFO'] = noondata[hfo_columns].apply(pd.to_numeric).sum(axis=1)
    noondata['LFO'] = noondata[lfo_columns].apply(pd.to_numeric).sum(axis=1)
    noondata['MDO_MGO'] = noondata[mdo_mgo_columns].apply(pd.to_numeric).sum(axis=1)
    noondata['totalco2']=pd.to_numeric(noondata['HFO'])*3.114+pd.to_numeric(noondata['LFO'])*3.151+pd.to_numeric(noondata['MDO_MGO'])*3.206
    agg_func = {'totalco2':'sum','miles_by_gps':'sum' ,'cargo_total':'mean'}
    df1 = noondata.groupby(['imo','eeoi_voyage_no']).agg(agg_func).reset_index()
    df1['cargo_distance']=df1['cargo_total']*df1['miles_by_gps']
    df1=df1.groupby(['imo'])[['totalco2','cargo_distance','cargo_total','miles_by_gps']].sum().reset_index()
    df1['EEOI 2022']=(pd.to_numeric(df1['totalco2']).fillna(0)*10**6)/pd.to_numeric(df1['cargo_distance'])
    merged_df =  pd.merge(df1, vessel_type[['imo','vessel_type','name']], how='left', left_on= "imo",  right_on = "imo")
    merged_df =  pd.merge(merged_df, deadweight[['imo','value']], how='left', left_on= "imo",  right_on = "imo")
    merged_df =  pd.merge(merged_df, gross_tonnage[['imo','value']], how='left', left_on= "imo",  right_on = "imo")
   
    merged_df.rename(columns={'value_x':'deadweight','value_y':'gross_tonnage','name':'vessel_name'}, inplace = True)
    
    
    # Define the condition for the vessels you want to filter
    condition = merged_df['vessel_type'].isin(["Bulk Carrier", "Combination Carrier", "Container", "Container Ship", "Gas Carrier", "General Cargo Ship", "LNG Carrier", "Refrigerated Cargo Carrier", "Ro-Ro Cargo Ship", "Tanker"])
    # Set the 'capacity' column to 2500 for rows that meet the condition
    merged_df.loc[condition, 'capacity'] = merged_df['deadweight']
   

    condition = merged_df['vessel_type'].isin(["Cruise Passenger Ship", "Ro-Ro Cargo Ship (Vehicle Carrier)", "Ro-Ro Passenger Ship", "ROPAX", "PCTC"])
    # Set the 'capacity' column to 2500 for rows that meet the condition
    merged_df.loc[condition, 'capacity'] = merged_df['gross_tonnage']

    def rqrd_eeoi(x,y,DWT_GT_ratio):
        if x:
            x=float(x)

            if y=='Container':

                return (174.22*(x)**-0.201)

            elif y=='Bulk Carrier':

                if (x>279000):

                    return (961.79*(279000)**-0.477)

                else:

                    return (961.79*(x)**-0.477)

            elif y=='Tanker':

                return (1218.8*(x)**-0.488)


            elif y=='ROPAX':


                if (x>10000):

                    return (902.59*(10000)**-0.381)

                elif (x<=10000):

                    return (902.59*(x)**-0.381)



            elif y=='PCTC':

                if DWT_GT_ratio<0.3:

                    a=((DWT_GT_ratio** - 0.7) * 780.36)

                    return (a*(x)**-0.471)


                elif DWT_GT_ratio>=0.3:

                        return (1812.63*(x)**-0.471)






            else:
                pass
        else:
            pass

    merged_df['DWT/GT']=pd.to_numeric(merged_df['deadweight'])/pd.to_numeric(merged_df['gross_tonnage'])
    merged_df['Requiredeeoi_2023'] = (merged_df.apply(lambda x: rqrd_eeoi(x['deadweight'], x['vessel_type'],x['DWT/GT']), axis=1)).round(2)


    def reduction_factor(x,y):
        if x:
            x=float(x)
   
            if y=='Bulk Carrier':
                x=float(x)
                if (x>=200000):
                    return 0.85
                elif (x>=20000) & (x<200000):
                    return 0.8
                elif (x>=10000) & (x<20000):
                    y2 = np.array([[0], [2], [4], [6], [8], [10], [12], [14], [16], [18], [20]])
                    X = np.array([[10000], [11000], [12000], [13000], [14000], [15000], [16000],[ 17000], [18000], [19000], [19999.99]])
                    model_2 = LinearRegression().fit(X, y2)
                    result_bulker = list(model_2.predict(np.array([[x]])))[0][0]
                    result_final = 1-(result_bulker/100)
                    return result_final
                elif  (x < 10000):
                    result =  0
                    return result
                else:
                    return np.nan
            elif y=='Tanker':
                if (x>=200000):
                    return 0.85
                elif (x>=20000) & (x<200000):
                    return 0.8
                elif (x>=4000) & (x<20000):
                    y2 = np.array([[0], [2], [4], [6], [8], [10], [12], [14], [16], [18], [20]])
                    X = np.array([[4000], [5600], [7200],  [8800], [10400], [ 12000], [13600], [15200], [16800],
                            [18400], [19999.99]])
                    model_2 = LinearRegression().fit(X, y2)
                    result_tanker = list(model_2.predict(np.array([[x]])))[0][0]
                    result_final = 1-(result_tanker/100)
                    return result_final
                elif (x < 4000):
                    result =  0
                    return result
       
                else:
                    return np.nan
            elif y=='Container':
                if x:
                    x=float(x)
                    if (x>=200000):
                        return 0.5
                    elif (x>=120000) & (x<200000):
                        return 0.55
                    elif (x>=80000) & (x<120000):
                        return 0.65
                    elif (x>=40000) & (x<80000):
                        return 0.7
                    elif (x>=15000) & (x<40000):
                        return 0.8
                    elif (x>=10000) & (x<15000):
                        y2 = np.array([[0], [2], [4], [6], [8], [10], [12], [14], [16], [18], [20]])
                        X = np.array([[10000], [10500], [11000], [11500], [12000], [12500], [13000], [13500], [14000], [14500],
                                [14999]])
           
                   
                        model_2 = LinearRegression().fit(X, y2)
                        result_container = list(model_2.predict(np.array([[x]])))[0][0]
                        result_final = 1-(result_container/100)
                        return result_final
                    elif (x < 10000):
                        result =  0
                        return result
                else:
                    pass      
            elif y=='ROPAX':
                if (x>=1000):
                    return 0.95
                elif (x>=250) & (x<1000):
                    y3 = np.array([[0], [1], [2], [3], [4], [5] ])
                    X = np.array([[250], [400], [550],  [700], [850], [ 1000]  ])
       
                    model_3 = LinearRegression().fit(X, y3)
                    result_ropax = list(model_3.predict(np.array([[x]])))[0][0]
                    result_final = 1-(result_ropax/100)
                    return result_final
                elif (x < 250):
                    result =  0
                    return result
                else:
                    return np.nan
            elif y=='PCTC':
                if (x>=10000):
                    return 0.85
                elif (x < 10000):
                    result =  0
                    return result
                else:
                    return np.nan
            else:
                return np.nan
        else:
            pass
   
    # merged_df['Reduction_Factor'] = merged_df.apply(lambda x: reduction_factor(x['deadweight'], x['vessel_type'])[0], axis=1)
    merged_df['Reduction_Factor'] = merged_df.apply(lambda x: reduction_factor(x['deadweight'], x['vessel_type']), axis=1)
    # merged_df['Reduction_Factor'] = (merged_df.apply(lambda x: reduction_factor(x['deadweight'], x['vessel_type']), axis=1))
    merged_df["Required EEOI"]=(pd.to_numeric(merged_df["Requiredeeoi_2023"])*pd.to_numeric(merged_df["Reduction_Factor"]))
# EEOI_active_vessel
    merged_df['A/R']=merged_df['EEOI 2022']/merged_df['Required EEOI']
    merged_df = merged_df.replace({np.nan:0})
    merged_df=merged_df.sort_values(by="A/R")
    merged_df["rank"] = merged_df["A/R"].rank(method='first')
    merged_df["rank"]=merged_df["rank"].astype(int)
    def calculate_rank(y):
        if y >= 0 and y <= 1.25:
            return "A_Rank"
        elif y > 1.25 and y <= 1.5:
            return "B_Rank"
        elif y > 1.5 and y <= 1.75:
            return "C_Rank"
        elif y > 1.75 and y <= 2:
            return "D_Rank"
        else:
            return "E_Rank"
    # Apply the custom function to the 'y' column to get the rank values
    merged_df['rating'] = merged_df['A/R'].apply(calculate_rank)
    def EEOI_rating_color(y):
        if y=="A_Rank":
            return "green"
        elif y=="B_Rank":
            return "lightgreen"
        elif y=="C_Rank":
            return "yellow"
        elif y=="D_Rank":
            return "orange"
        elif y=="E_Rank":
            return "red"
        
    merged_df['color'] = merged_df.apply(lambda x: EEOI_rating_color(x['rating']), axis=1)
    merged_df=merged_df[["vessel_name","rank",'deadweight',"EEOI 2022","rating",'Required EEOI',"color","A/R",'imo','vessel_type']].round(2)
    merged_df.rename(columns={'EEOI 2022':'EEOI '+str(current_year)},inplace=True)
    
    
    bulker = merged_df[merged_df['vessel_type']=='Bulk Carrier']
    bulker["rank"] = bulker["A/R"].rank(method='first')
    bulker=bulker.to_json(orient="records")
    bulker=json.loads(bulker)
    
    
    container = merged_df[merged_df['vessel_type']=='Container']
    container["rank"] = container["A/R"].rank(method='first')
    container=container.to_json(orient="records")
    container=json.loads(container)
    
    pctc = merged_df[merged_df['vessel_type']=='PCTC']
    pctc["rank"] = pctc["A/R"].rank(method='first')
    pctc=pctc.to_json(orient="records")
    pctc=json.loads(pctc)
    
    ropax = merged_df[merged_df['vessel_type']=='ROPAX']
    ropax["rank"] = ropax["A/R"].rank(method='first')
    ropax=ropax.to_json(orient="records")
    ropax=json.loads(ropax)
    
    tug = merged_df[merged_df['vessel_type']=='TUG']
    tug["rank"] = tug["A/R"].rank(method='first')
    tug=tug.to_json(orient="records")
    tug=json.loads(tug)


    ro = merged_df[merged_df['vessel_type']=='Ro-Ro']
    ro["rank"] = ro["A/R"].rank(method='first')
    ro=ro.to_json(orient="records")
    ro=json.loads(ro)
    
    
    
    
    
    


    # merged_df=merged_df.to_json(orient="records")
    # merged_df=json.loads(merged_df)
    return {
            'df_time_Container':container,
            'df_time_Bulker':bulker,
            'df_time_pctc':pctc,
            'df_time_ropax':ropax,
            # 'df_time_tug':tug
            'df_time_ro':ro
            }
