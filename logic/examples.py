"""Synthetic cases retained for demos and downloadable templates."""
import numpy as np
import pandas as pd
from .validation import SCREENING_COLUMNS

def example_screening_dataframe() -> pd.DataFrame:
    df = pd.DataFrame([
        {"sample_id":"CASE-BTT-001","age":24,"sex":"Female","hb_g_dl":11.2,"rbc_10e12_l":5.8,"hct_percent":35,"mcv_fl":67,"mch_pg":20.5,"mchc_g_dl":31.2,"rdw_percent":14.2,"retic_percent":1.2,"ferritin_ng_ml":85,"hba_percent":94,"hba2_percent":5.1,"hbf_percent":1.2,"hbe_percent":0,"oft":"Positive","dcip":"Negative","hbh_inclusion":"Negative","transfusion_recent":False,"pregnant":False,"smear_target_cells":True,"family_history":True},
        {"sample_id":"CASE-HBE-002","age":29,"sex":"Male","hb_g_dl":12.4,"rbc_10e12_l":5.2,"hct_percent":38,"mcv_fl":74,"mch_pg":23,"mchc_g_dl":31,"rdw_percent":14,"retic_percent":1.0,"ferritin_ng_ml":90,"hba_percent":72,"hba2_percent":3.8,"hbf_percent":0.8,"hbe_percent":23.5,"oft":"Positive","dcip":"Positive","hbh_inclusion":"Negative","transfusion_recent":False,"pregnant":False,"smear_target_cells":True,"family_history":False},
        {"sample_id":"CASE-ALPHA-003","age":19,"sex":"Female","hb_g_dl":11.8,"rbc_10e12_l":5.7,"hct_percent":36,"mcv_fl":69,"mch_pg":21,"mchc_g_dl":32,"rdw_percent":13.7,"retic_percent":1.3,"ferritin_ng_ml":110,"hba_percent":96.7,"hba2_percent":2.5,"hbf_percent":0.4,"hbe_percent":0,"oft":"Positive","dcip":"Negative","hbh_inclusion":"Negative","transfusion_recent":False,"pregnant":False,"smear_target_cells":False,"family_history":True},
        {"sample_id":"CASE-HBH-004","age":33,"sex":"Female","hb_g_dl":8.8,"rbc_10e12_l":5.9,"hct_percent":30,"mcv_fl":58,"mch_pg":18,"mchc_g_dl":30,"rdw_percent":18.5,"retic_percent":3.2,"ferritin_ng_ml":135,"hba_percent":88,"hba2_percent":1.8,"hbf_percent":0.9,"hbe_percent":0,"oft":"Positive","dcip":"Negative","hbh_inclusion":"Positive","transfusion_recent":False,"pregnant":False,"smear_target_cells":True,"family_history":True},
        {"sample_id":"CASE-IDA-005","age":38,"sex":"Female","hb_g_dl":9.7,"rbc_10e12_l":4.2,"hct_percent":31,"mcv_fl":72,"mch_pg":22,"mchc_g_dl":30.6,"rdw_percent":18.2,"retic_percent":0.9,"ferritin_ng_ml":8,"hba_percent":97,"hba2_percent":2.6,"hbf_percent":0.3,"hbe_percent":0,"oft":"Negative","dcip":"Negative","hbh_inclusion":"Negative","transfusion_recent":False,"pregnant":False,"smear_target_cells":False,"family_history":False},
        {"sample_id":"CASE-BORDER-006","age":30,"sex":"Male","hb_g_dl":13.5,"rbc_10e12_l":5.4,"hct_percent":41,"mcv_fl":79,"mch_pg":26,"mchc_g_dl":32,"rdw_percent":14.8,"retic_percent":1.0,"ferritin_ng_ml":34,"hba_percent":95.8,"hba2_percent":3.4,"hbf_percent":0.9,"hbe_percent":0,"oft":"Positive","dcip":"Negative","hbh_inclusion":"Negative","transfusion_recent":False,"pregnant":False,"smear_target_cells":False,"family_history":False},
    ])
    df["hba2e_percent"] = np.nan
    # Optional channels remain missing until independently measured.
    df["bart_percent"] = np.nan
    df["hbh_percent"] = np.nan
    df["hbcs_percent"] = np.nan
    df["hb_method"] = "HPLC"
    return df[[c for c in SCREENING_COLUMNS if c in df.columns]]

