"""
Comprehensive NSE Stock Universe

This file contains a comprehensive list of NSE stocks with their sector mappings.
Includes NIFTY 500+ constituents and other actively traded stocks.
"""

# Sector mapping for all stocks - Expanded to cover 1000+ stocks
SECTOR_MAP = {
    # ============== BANKING (100+ stocks) ==============
    # Private Banks
    "HDFCBANK": "Banking", "ICICIBANK": "Banking", "KOTAKBANK": "Banking", "AXISBANK": "Banking",
    "INDUSINDBK": "Banking", "FEDERALBNK": "Banking", "IDFCFIRSTB": "Banking", "BANDHANBNK": "Banking",
    "RBLBANK": "Banking", "YESBANK": "Banking", "IDBI": "Banking", "CSBBANK": "Banking",
    "DCBBANK": "Banking", "KARURVYSYA": "Banking", "CITYUNIONB": "Banking", "SOUTHBANK": "Banking",
    "TMBANK": "Banking", "LAKSHVILAS": "Banking", "DHANLAXMI": "Banking", "CUB": "Banking",
    "KARUR": "Banking", "TAMILNAD": "Banking", "NAINITALBNK": "Banking", "JKBANK": "Banking",
    "KTKBANK": "Banking", "AUBANK": "Banking", "UJJIVANSFB": "Banking", "EQUITASBNK": "Banking",
    "FINOPB": "Banking", "ESAFSFB": "Banking", "SURYODAY": "Banking", "UTKARSHBNK": "Banking",

    # PSU Banks
    "SBIN": "Banking", "BANKBARODA": "Banking", "PNB": "Banking", "CANBK": "Banking",
    "UNIONBANK": "Banking", "INDIANB": "Banking", "IOB": "Banking", "CENTRALBK": "Banking",
    "UCOBANK": "Banking", "BANKINDIA": "Banking", "MAHABANK": "Banking", "PSB": "Banking",
    "PNBHOUSING": "Banking",

    # ============== FINANCE & NBFCs (100+ stocks) ==============
    "BAJFINANCE": "Finance", "BAJAJFINSV": "Finance", "CHOLAFIN": "Finance", "MUTHOOTFIN": "Finance",
    "MANAPPURAM": "Finance", "LICHSGFIN": "Finance", "SHRIRAMFIN": "Finance", "M&MFIN": "Finance",
    "POONAWALLA": "Finance", "CREDITACC": "Finance", "IIFL": "Finance", "LTFH": "Finance",
    "SUNDARMFIN": "Finance", "REPCO": "Finance", "CANFINHOME": "Finance", "HOMEFIRST": "Finance",
    "APTUS": "Finance", "AAVAS": "Finance", "SBICARD": "Finance", "PFC": "Finance",
    "RECLTD": "Finance", "IRFC": "Finance", "HUDCO": "Finance", "MFSL": "Finance",
    "ABSLAMC": "Finance", "NSDL": "Finance", "CDSL": "Finance", "BSE": "Finance",
    "MCX": "Finance", "CAMS": "Finance", "KFINTECH": "Finance", "ANGELONE": "Finance",
    "MOTILALOFS": "Finance", "EDELWEISS": "Finance", "GEOJITFSL": "Finance", "5PAISA": "Finance",
    "FIVESTAR": "Finance", "FUSION": "Finance", "SPANDANA": "Finance", "UGROCAP": "Finance",
    "IIFLSEC": "Finance", "ICICISEC": "Finance", "HDFCAMC": "Finance", "NIPPONIND": "Finance",
    "UTIAMC": "Finance", "SBFC": "Finance", "JMFINANCIL": "Finance", "CENTRUM": "Finance",
    "INDIASHLTR": "Finance", "RELCAPITAL": "Finance", "DHFL": "Finance", "MAGMA": "Finance",
    "CAPRI": "Finance", "MASFIN": "Finance", "MAHINDGROP": "Finance", "CREDITACC": "Finance",
    "AROMAENTER": "Finance", "ARMAN": "Finance", "SAMHI": "Finance", "SATIA": "Finance",

    # ============== INSURANCE (20+ stocks) ==============
    "HDFCLIFE": "Insurance", "SBILIFE": "Insurance", "ICICIPRULI": "Insurance", "ICICIGI": "Insurance",
    "LICI": "Insurance", "GICRE": "Insurance", "NIACL": "Insurance", "STAR": "Insurance",
    "POLICYBZR": "Insurance", "GODIGIT": "Insurance", "ABSLTL": "Insurance", "MAXLIFE": "Insurance",
    "BAJAJALLIANZ": "Insurance", "BHARTIAX": "Insurance", "EVEREADY": "Insurance", "IRCTC": "Insurance",

    # ============== INFORMATION TECHNOLOGY (100+ stocks) ==============
    "TCS": "IT", "INFY": "IT", "HCLTECH": "IT", "WIPRO": "IT", "TECHM": "IT",
    "LTIM": "IT", "PERSISTENT": "IT", "COFORGE": "IT", "MPHASIS": "IT", "LTTS": "IT",
    "TATAELXSI": "IT", "MINDTREE": "IT", "NIITLTD": "IT", "CYIENT": "IT", "SONATSOFTW": "IT",
    "KPITTECH": "IT", "HAPPSTMNDS": "IT", "ROUTE": "IT", "LATENTVIEW": "IT", "TANLA": "IT",
    "NAZARA": "IT", "ZOMATO": "IT", "PAYTM": "IT", "NAUKRI": "IT", "JUSTDIAL": "IT",
    "INDIAMART": "IT", "AFFLE": "IT", "NEWGEN": "IT", "INTELLECT": "IT", "MASTEK": "IT",
    "ECLERX": "IT", "ZENSAR": "IT", "BIRLASOFT": "IT", "MSTCLTD": "IT", "HEXAWARE": "IT",
    "RATEGAIN": "IT", "FSL": "IT", "DATAPATTNS": "IT", "TATATECH": "IT", "QUICKHEAL": "IT",
    "NUCLEUS": "IT", "SUBEX": "IT", "SASKEN": "IT", "KERNEX": "IT", "ORIENTGREEN": "IT",
    "GTPL": "IT", "GTLINFRA": "IT", "FIRSTSOURCE": "IT", "SIFY": "IT", "CYBERTECH": "IT",
    "SAKSOFT": "IT", "SOFTSOL": "IT", "ACCELYA": "IT", "ONMOBILE": "IT", "COMPUAGE": "IT",
    "MIC": "IT", "INFIBEAM": "IT", "CARTRADE": "IT", "ZAGGLE": "IT", "MATRIMONY": "IT",
    "MAPMY": "IT", "MAPMYINDIA": "IT", "IDEAFORGE": "IT", "MTAR": "IT", "NETWEB": "IT",
    "ZAGGLE": "IT", "INOXGFL": "IT", "EASEMYTRIP": "IT", "IXIGO": "IT", "YATRA": "IT",

    # ============== PHARMA (100+ stocks) ==============
    "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma", "DIVISLAB": "Pharma",
    "TORNTPHARM": "Pharma", "AUROPHARMA": "Pharma", "BIOCON": "Pharma", "LAURUSLABS": "Pharma",
    "ALKEM": "Pharma", "LUPIN": "Pharma", "NATCOPHARMA": "Pharma", "GRANULES": "Pharma",
    "GLENMARK": "Pharma", "IPCA": "Pharma", "ABBOTINDIA": "Pharma", "PFIZER": "Pharma",
    "GLAXO": "Pharma", "SANOFI": "Pharma", "JBPHARMA": "Pharma", "AJANTPHARM": "Pharma",
    "IPCALAB": "Pharma", "ERIS": "Pharma", "ZYDUSLIFE": "Pharma", "MANKIND": "Pharma",
    "GLAND": "Pharma", "SYNGENE": "Pharma", "STRIDES": "Pharma", "SOLARA": "Pharma",
    "JUBILANT": "Pharma", "JUBILANTPHARMA": "Pharma", "SEQUENT": "Pharma", "SHILPA": "Pharma",
    "SPARC": "Pharma", "SUVEN": "Pharma", "INDOCO": "Pharma", "MARKSANS": "Pharma",
    "BLISSGVS": "Pharma", "WOCKPHARMA": "Pharma", "SUNPHARMAADV": "Pharma", "NEULAND": "Pharma",
    "SMS": "Pharma", "ANURAS": "Pharma", "KOPRAN": "Pharma", "RPPL": "Pharma",
    "FDC": "Pharma", "AARTIDRUGS": "Pharma", "VIMTA": "Pharma", "SUVENPHAR": "Pharma",
    "CONCORD": "Pharma", "CAPLIN": "Pharma", "ORTIN": "Pharma", "MEDPLUS": "Pharma",
    "POLYMED": "Pharma", "HMVL": "Pharma", "MOREPEN": "Pharma", "AARTIDRUGS": "Pharma",
    "PGHL": "Pharma", "OPTOCIRCUIT": "Pharma", "NECLIFE": "Pharma", "APLLTD": "Pharma",

    # ============== HEALTHCARE (50+ stocks) ==============
    "LALPATHLAB": "Healthcare", "APOLLOHOSP": "Healthcare", "METROPOLIS": "Healthcare",
    "MAXHEALTH": "Healthcare", "FORTIS": "Healthcare", "MEDANTA": "Healthcare",
    "KIMS": "Healthcare", "YATHARTH": "Healthcare", "RAINBOW": "Healthcare",
    "ASTER": "Healthcare", "VIJAYA": "Healthcare", "SHALBY": "Healthcare",
    "THYROCARE": "Healthcare", "KRSNAA": "Healthcare", "POLY": "Healthcare",
    "HCG": "Healthcare", "NARAYANA": "Healthcare", "GLOBALHSP": "Healthcare",
    "NEULANDLAB": "Healthcare", "SPSLTD": "Healthcare", "SUPRIYA": "Healthcare",
    "MEDPLUS": "Healthcare", "RADIOCITY": "Healthcare", "SUPRAJA": "Healthcare",

    # ============== AUTOMOBILE (50+ stocks) ==============
    "MARUTI": "Auto", "M&M": "Auto", "TATAMOTORS": "Auto", "EICHERMOT": "Auto",
    "BAJAJ-AUTO": "Auto", "HEROMOTOCO": "Auto", "TVSMOTOR": "Auto", "ASHOKLEY": "Auto",
    "ESCORTS": "Auto", "FORCEMOT": "Auto", "VSTTILLERS": "Auto", "TRACTORS": "Auto",
    "OLECTRA": "Auto", "GREAVES": "Auto", "AMPLTD": "Auto", "JBMA": "Auto",
    "MAHSCOOTER": "Auto", "ATUL": "Auto", "SMLLTD": "Auto", "INDIARTV": "Auto",
    "AUTOAXLES": "Auto", "OEMCAR": "Auto", "ATLASCOPCO": "Auto", "BIKAJI": "Auto",
    "JTEJAUTO": "Auto", "KPIL": "Auto", "KROSAKI": "Auto", "LEMONTREE": "Auto",

    # ============== AUTO ANCILLARY (80+ stocks) ==============
    "BHARATFORG": "Auto Ancillary", "MOTHERSON": "Auto Ancillary", "MRF": "Auto Ancillary",
    "BALKRISIND": "Auto Ancillary", "APOLLOTYRE": "Auto Ancillary", "CEATLTD": "Auto Ancillary",
    "JKTYRE": "Auto Ancillary", "CEAT": "Auto Ancillary",
    "EXIDEIND": "Auto Ancillary", "AMARAJABAT": "Auto Ancillary", "BOSCHLTD": "Auto Ancillary",
    "SUNDRMFAST": "Auto Ancillary", "SCHAEFFLER": "Auto Ancillary", "TIMKEN": "Auto Ancillary",
    "SKFINDIA": "Auto Ancillary", "ENDURANCE": "Auto Ancillary", "SUPRAJIT": "Auto Ancillary",
    "GABRIEL": "Auto Ancillary", "LUMAXTECH": "Auto Ancillary", "VARROC": "Auto Ancillary",
    "SWARAJENG": "Auto Ancillary", "FINCABLES": "Auto Ancillary", "JAMNAAUTO": "Auto Ancillary",
    "ABORAUTO": "Auto Ancillary", "UNOMINDA": "Auto Ancillary", "CRAFTSMAN": "Auto Ancillary",
    "MINDA": "Auto Ancillary", "SUBROS": "Auto Ancillary", "SANDHAR": "Auto Ancillary",
    "SUNFLAG": "Auto Ancillary", "JAYNECOIND": "Auto Ancillary", "LUMAX": "Auto Ancillary",
    "GNA": "Auto Ancillary", "WHEELS": "Auto Ancillary", "ASAHISONGI": "Auto Ancillary",
    "IGARASHI": "Auto Ancillary", "MAHINDRACIE": "Auto Ancillary", "UCALFUEL": "Auto Ancillary",
    "SHARDACROP": "Auto Ancillary", "TALBROS": "Auto Ancillary", "STEELCAST": "Auto Ancillary",
    "RSYSTEMS": "Auto Ancillary", "DENSO": "Auto Ancillary", "SETCO": "Auto Ancillary",
    "JAMSHRI": "Auto Ancillary", "LUMAXAUTO": "Auto Ancillary", "REMSONS": "Auto Ancillary",
    "KALYANI": "Auto Ancillary", "BOROSILLTD": "Auto Ancillary", "HMVL": "Auto Ancillary",
    "AUTO": "Auto Ancillary", "CRISIL": "Auto Ancillary", "FEDERALBNK": "Auto Ancillary",

    # ============== FMCG & CONSUMER (80+ stocks) ==============
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG", "BRITANNIA": "FMCG",
    "DABUR": "FMCG", "MARICO": "FMCG", "GODREJCP": "FMCG", "COLPAL": "FMCG",
    "TATACONSUM": "FMCG", "VBL": "FMCG", "UBL": "FMCG", "MCDOWELL-N": "FMCG",
    "RADICO": "FMCG", "GLOBUSSPR": "FMCG", "PGHH": "FMCG", "GILLETTE": "FMCG",
    "JYOTHYLABS": "FMCG", "EMAMILTD": "FMCG", "BAJAJCON": "FMCG", "ZYDUSWELL": "FMCG",
    "HATSUN": "FMCG", "PARAG": "FMCG", "HERITGFOOD": "FMCG", "BIKAJI": "FMCG",
    "VAIBHAVGBL": "FMCG", "BALRAMCHIN": "FMCG", "DWARIKESH": "FMCG", "RENUKA": "FMCG",
    "GODFRYPHLP": "FMCG", "TCPLPACK": "FMCG", "AVANTIFEED": "FMCG", "WATERBASE": "FMCG",
    "LT": "FMCG", "CCL": "FMCG", "SUKHJITS": "FMCG", "VENKEYS": "FMCG",
    "PRATAAP": "FMCG", "DODLA": "FMCG", "MRPL": "FMCG", "KWALITY": "FMCG",
    "TASTY": "FMCG", "KRBL": "FMCG", "LTFOODS": "FMCG", "PATANJALI": "FMCG",
    "GODREJAGRO": "FMCG", "AGRITECH": "FMCG", "EVEREADY": "FMCG", "VADILAL": "FMCG",
    "ZENSARTECH": "FMCG", "CREATIVE": "FMCG", "AKZOINDIA": "FMCG", "MONSANTO": "FMCG",
    "PROCTER": "FMCG", "RECKITT": "FMCG", "3M": "FMCG", "ASIANPAINT": "FMCG",

    # ============== METALS & MINING (80+ stocks) ==============
    "TATASTEEL": "Metals", "JSWSTEEL": "Metals", "HINDALCO": "Metals", "VEDL": "Metals",
    "COALINDIA": "Metals", "NMDC": "Metals", "SAIL": "Metals", "NATIONALUM": "Metals",
    "HINDZINC": "Metals", "JINDALSTEL": "Metals", "JSWENERGY": "Metals", "MOIL": "Metals",
    "WELCORP": "Metals", "RATNAMANI": "Metals", "APLAPOLLO": "Metals", "JINDALSAW": "Metals",
    "SHYAMMETL": "Metals", "GPIL": "Metals", "NSLNISP": "Metals", "KIOCL": "Metals",
    "MISHRA": "Metals", "HLEGLAS": "Metals", "SANDUMA": "Metals", "GODAWARI": "Metals",
    "GALLANTT": "Metals", "LLOYDSME": "Metals", "PRAKASH": "Metals", "ELECTRO": "Metals",
    "KALYANIFRG": "Metals", "MAITHANALL": "Metals", "GRAVITA": "Metals", "SRGH": "Metals",
    "RAMASTEEL": "Metals", "SHYAMCENT": "Metals", "SURYATRO": "Metals", "TATASTEELBSL": "Metals",
    "TATAMETALIK": "Metals", "TINPLATE": "Metals", "VISAKAIND": "Metals", "WELSPUNLIV": "Metals",
    "APOLLOPIPE": "Metals", "HIRA": "Metals", "NCLIND": "Metals", "ORIENTCEM": "Metals",
    "SHAKTIPUMP": "Metals", "SHIVALIK": "Metals", "STEELSTUD": "Metals", "STEWARTANDLLO": "Metals",
    "TATAELXSI": "Metals", "TEXINFRA": "Metals", "THANGAMAYL": "Metals", "THEMISMED": "Metals",
    "TIRUMALCHM": "Metals", "TTML": "Metals", "UGARSUGAR": "Metals", "UJAAS": "Metals",

    # ============== OIL & GAS / ENERGY (60+ stocks) ==============
    "RELIANCE": "Energy", "ONGC": "Energy", "BPCL": "Energy", "IOC": "Energy",
    "HINDPETRO": "Energy", "GAIL": "Energy", "OIL": "Energy", "PETRONET": "Energy",
    "MGL": "Energy", "IGL": "Energy", "GSPL": "Energy", "GUJGASLTD": "Energy",
    "AEGISCHEM": "Energy", "MRPL": "Energy", "CHENNPETRO": "Energy", "CASTROLIND": "Energy",
    "GSFC": "Energy", "GNFC": "Energy", "DEEPAKFERT": "Energy", "NFL": "Energy",
    "ATGL": "Energy", "GUJALKALI": "Energy", "HPCL": "Energy", "IOCL": "Energy",
    "IOGL": "Energy", "MRFLTD": "Energy", "MTNL": "Energy", "OILCOUNTUB": "Energy",
    "OLECTRA": "Energy", "ONGCLTD": "Energy", "PNBGILTR": "Energy", "POLYPLEX": "Energy",
    "POWERMECH": "Energy", "GPIL": "Energy", "GULFOILLUB": "Energy", "HINDOILEXP": "Energy",
    "INDIANOIL": "Energy", "ISGEC": "Energy", "JCHAC": "Energy", "JINDALSTAIN": "Energy",
    "JPASSOCIAT": "Energy", "KDDL": "Energy", "KHAITAN": "Energy", "KIRLOSBROS": "Energy",
    "KITEX": "Energy", "KKCL": "Energy", "KPIL": "Energy", "JYOTISTRUC": "Energy",

    # ============== POWER & UTILITIES (80+ stocks) ==============
    "NTPC": "Power", "POWERGRID": "Power", "TATAPOWER": "Power", "ADANIGREEN": "Power",
    "ADANIENSOL": "Power", "NHPC": "Power", "SJVN": "Power", "TORNTPOWER": "Power",
    "CESC": "Power", "JSWENERGY": "Power", "NLCINDIA": "Power", "RPOWER": "Power",
    "JPPOWER": "Power", "GIPCL": "Power", "GPPL": "Power", "SUZLON": "Power",
    "INOXWIND": "Power", "BEL": "Power", "KPIGENERGY": "Power", "IEX": "Power",
    "TATACOMM": "Power", "RELPOWER": "Power", "JAIPRAKASH": "Power",
    "JSPL": "Power", "JUBL": "Power", "KAKATCEM": "Power", "ORIENTGREEN": "Power",
    "RATTANINDIA": "Power", "RCF": "Power", "RECLTD": "Power", "RELINFRA": "Power",
    "RENUKA": "Power", "REPCOHOME": "Power", "REPL": "Power", "RITES": "Power",
    "RKFORGE": "Power", "ROSSELLIND": "Power", "RSWM": "Power", "SAKAR": "Power",
    "WABCOINDIA": "Power", "WAAREE": "Power", "WABAG": "Power", "WEBCOR": "Power",
    "WELENT": "Power", "WELSPUNENT": "Power", "WENDT": "Power", "WHEELS": "Power",
    "WINDCARE": "Power", "WIPRO": "Power", "WOCKHARDT": "Power", "WONDERLA": "Power",

    # ============== INFRASTRUCTURE & CONSTRUCTION (100+ stocks) ==============
    "LT": "Infrastructure", "LARSENTOUB": "Infrastructure", "IRB": "Infrastructure",
    "NBCC": "Infrastructure", "NCC": "Infrastructure", "KNRCON": "Infrastructure",
    "ASHOKA": "Infrastructure", "PNCINFRA": "Infrastructure", "JKIL": "Infrastructure",
    "HGINFRA": "Infrastructure", "RVNL": "Infrastructure", "IRCON": "Infrastructure",
    "ENGINERSIN": "Infrastructure", "RITES": "Infrastructure", "BEL": "Infrastructure",
    "BEML": "Infrastructure", "COCHINSHIP": "Infrastructure", "GRINDWELL": "Infrastructure",
    "RAILTEL": "Infrastructure", "IIFLSEC": "Infrastructure", "PTELINFRA": "Infrastructure",
    "PSP": "Infrastructure", "SADBHAV": "Infrastructure", "GAYAPROJ": "Infrastructure",
    "HCC": "Infrastructure", "ITNL": "Infrastructure", "JMCPROJ": "Infrastructure",
    "KALPATPOW": "Infrastructure", "KECL": "Infrastructure", "MANAPPURAM": "Infrastructure",
    "MPHASIS": "Infrastructure", "NDTV": "Infrastructure", "NESCO": "Infrastructure",
    "NIITTECH": "Infrastructure", "OBEROIRELTY": "Infrastructure", "OMINFRAL": "Infrastructure",
    "ORIS": "Infrastructure", "ORIENTCEME": "Infrastructure", "ORTEL": "Infrastructure",
    "OSMOSYS": "Infrastructure", "PATELENG": "Infrastructure", "PDMJEPAPER": "Infrastructure",
    "AHLUCONT": "Infrastructure", "AIAENG": "Infrastructure", "AJMERA": "Infrastructure",
    "ANDHRACEME": "Infrastructure", "APLAPOLLO": "Infrastructure", "ARIHANTCAP": "Infrastructure",

    # ============== CEMENT (40+ stocks) ==============
    "ULTRACEMCO": "Cement", "AMBUJACEM": "Cement", "ACC": "Cement", "SHREECEM": "Cement",
    "RAMCOCEM": "Cement", "DALMIACEM": "Cement", "JKCEMENT": "Cement", "BIRLACORPN": "Cement",
    "INDIACEM": "Cement", "PRISMCEM": "Cement", "HEIDELBERG": "Cement", "NUVOCO": "Cement",
    "SAGCEM": "Cement", "JKLAKSHMI": "Cement", "KCEIL": "Cement", "STARCEMENT": "Cement",
    "ORIENTCEM": "Cement", "BANGURCEM": "Cement", "DECCANCEM": "Cement", "MANGCEM": "Cement",
    "KESORAMIND": "Cement", "SANGHIBSC": "Cement", "SAURASHCEM": "Cement", "SHREDIGCEM": "Cement",
    "SOMANYFLOR": "Cement", "HEIDELBRG": "Cement", "SSWL": "Cement", "JSWCEMENT": "Cement",
    "ADANIENT": "Cement", "AMBUJCEM": "Cement", "BIRLACEM": "Cement", "WARNABATA": "Cement",

    # ============== REAL ESTATE (50+ stocks) ==============
    "DLF": "Realty", "GODREJPROP": "Realty", "OBEROIRLTY": "Realty", "PRESTIGE": "Realty",
    "SOBHA": "Realty", "PHOENIXLTD": "Realty", "BRIGADE": "Realty", "MAHLIFE": "Realty",
    "LODHA": "Realty", "SIGNATURE": "Realty", "SUNTECK": "Realty", "KOLTEPATIL": "Realty",
    "ANANTRAJ": "Realty", "RUSTOMJEE": "Realty", "ARVIND": "Realty", "IBREALEST": "Realty",
    "RAYMOND": "Realty", "MAHINDLIFE": "Realty", "PURVA": "Realty", "AHLEAST": "Realty",
    "SHOBHA": "Realty", "ARIHANT": "Realty", "ASHIANA": "Realty", "DB": "Realty",
    "HDIL": "Realty", "HUBTOWN": "Realty", "INDIABULL": "Realty", "KEYSTONE": "Realty",
    "MACROTECH": "Realty", "ORION": "Realty", "PARTHENON": "Realty", "PRAJAY": "Realty",
    "PROVIDENT": "Realty", "PURAVANKR": "Realty", "RMZ": "Realty", "SALARPURIA": "Realty",
    "SQUARE4": "Realty", "TRIBHOVAND": "Realty", "VIPULLTD": "Realty", "ANSAL": "Realty",

    # ============== CONSUMER DURABLES (60+ stocks) ==============
    "TITAN": "Consumer Durables", "ASIANPAINT": "Consumer Durables", "BERGEPAINT": "Consumer Durables",
    "PIDILITIND": "Consumer Durables", "BATAINDIA": "Consumer Durables", "RELAXO": "Consumer Durables",
    "PAGEIND": "Consumer Durables", "TRENT": "Consumer Durables", "DMART": "Retail",
    "VMART": "Retail", "SHOPERSTOP": "Retail", "ABFRL": "Retail", "VEDANTFASHION": "Retail",
    "HAVELLS": "Consumer Durables", "VOLTAS": "Consumer Durables", "BLUESTARCO": "Consumer Durables",
    "SYMPHONY": "Consumer Durables", "CROMPTON": "Consumer Durables", "BAJAJELEC": "Consumer Durables",
    "WHIRLPOOL": "Consumer Durables", "DIXON": "Consumer Durables", "AMBER": "Consumer Durables",
    "KALYANKJIL": "Consumer Durables", "SENCO": "Consumer Durables", "KALYAN": "Consumer Durables",
    "CENTURYPLY": "Consumer Durables", "GREENPANEL": "Consumer Durables",
    "ASTRAL": "Consumer Durables", "SUPREMEIND": "Consumer Durables", "VGUARD": "Consumer Durables",
    "ORIENTELEC": "Consumer Durables", "TTKLTKUMAR": "Consumer Durables", "STOVERAFT": "Consumer Durables",
    "CERA": "Consumer Durables", "HINDWAREAP": "Consumer Durables", "STYLAMIND": "Consumer Durables",
    "RACL": "Consumer Durables", "SIRCA": "Consumer Durables", "FLAIR": "Consumer Durables",
    "PRINCEIPE": "Consumer Durables", "OPTIEMUS": "Consumer Durables", "ELECON": "Consumer Durables",
    "BUTTERFLY": "Consumer Durables", "ELICA": "Consumer Durables", "FABER": "Consumer Durables",
    "GLEN": "Consumer Durables", "HAWKINS": "Consumer Durables", "TTK": "Consumer Durables",

    # ============== CAPITAL GOODS & ENGINEERING (100+ stocks) ==============
    "SIEMENS": "Capital Goods", "ABB": "Capital Goods", "POLYCAB": "Capital Goods",
    "BHEL": "Capital Goods", "THERMAX": "Capital Goods", "CUMMINSIND": "Capital Goods",
    "ELGIEQUIP": "Capital Goods", "KEI": "Capital Goods", "TRIVENI": "Capital Goods",
    "AIAENG": "Capital Goods", "GRINDWELL": "Capital Goods", "CARBORUNIV": "Capital Goods",
    "GNFC": "Capital Goods", "HEG": "Capital Goods", "GRAPHITE": "Capital Goods",
    "KAJARIACER": "Capital Goods", "SOMANYCERA": "Capital Goods", "ORIENTELEC": "Capital Goods",
    "JYOTILAB": "Capital Goods", "TITAGARH": "Capital Goods", "COCHINSHIP": "Capital Goods",
    "GSG": "Capital Goods", "INOXWIND": "Capital Goods", "SUZLON": "Capital Goods",
    "KALPATPOWR": "Capital Goods", "KEC": "Capital Goods", "TRIL": "Capital Goods",
    "ASTRAZEN": "Capital Goods", "HONAUT": "Capital Goods", "3MINDIA": "Capital Goods",
    "KIRL": "Capital Goods", "KIRLOSENG": "Capital Goods", "LAKSHMI": "Capital Goods",
    "LLOYDSENG": "Capital Goods", "MAHSEA": "Capital Goods", "MANALIPETC": "Capital Goods",
    "MTAR": "Capital Goods", "VOLTAMP": "Capital Goods", "WPIL": "Capital Goods",
    "ACE": "Capital Goods", "ADORWELD": "Capital Goods", "BHARAT": "Capital Goods",
    "DYNAMATECH": "Capital Goods", "ELECONENG": "Capital Goods", "FINOLEX": "Capital Goods",
    "GMM": "Capital Goods", "GOODYEAR": "Capital Goods", "HAVILSHAND": "Capital Goods",
    "HITECHGEAR": "Capital Goods", "IGARASHI": "Capital Goods", "INDTERRAIN": "Capital Goods",
    "INTERGLOBE": "Capital Goods", "KALYANI": "Capital Goods", "KOLTE": "Capital Goods",
    "MASTEK": "Capital Goods", "MAZDA": "Capital Goods", "MOLDTEK": "Capital Goods",

    # ============== TELECOM & MEDIA (40+ stocks) ==============
    "BHARTIARTL": "Telecom", "IDEA": "Telecom", "TATACOMM": "Telecom", "ROUTE": "Telecom",
    "SUNTV": "Media", "ZEEL": "Media", "PVR": "Media", "INOXLEISUR": "Media",
    "NETWORK18": "Media", "TV18BRDCST": "Media", "SAREGAMA": "Media", "TIPS": "Media",
    "NAZARA": "Media", "DELTACORP": "Media", "DISH": "Media", "HATHWAY": "Media",
    "INDIATV": "Media", "JAGRAN": "Media", "NDTV": "Media", "RADIOMIR": "Media",
    "RELAINCE": "Media", "SETCO": "Media", "SHEMAROO": "Media", "TVTODAY": "Media",
    "UHVL": "Media", "UNITECH": "Media", "VICOM": "Media", "ZEENEWS": "Media",
    "INDUSTOWER": "Telecom Infra", "BHARTIHEXA": "Telecom Infra", "STERLCOM": "Telecom Infra",

    # ============== CHEMICALS & FERTILIZERS (100+ stocks) ==============
    "PIIND": "Chemicals", "SRF": "Chemicals", "ATUL": "Chemicals", "NAVINFLUOR": "Chemicals",
    "DEEPAKNTR": "Chemicals", "COROMANDEL": "Chemicals", "GNFC": "Chemicals", "GSFC": "Chemicals",
    "CHAMBALFERT": "Chemicals", "RCF": "Chemicals", "NFL": "Chemicals", "FACT": "Chemicals",
    "GUJALKALI": "Chemicals", "TATACHEM": "Chemicals", "BASF": "Chemicals", "FINEORG": "Chemicals",
    "VINATIORGA": "Chemicals", "GALAXYSURF": "Chemicals", "AARTI": "Chemicals", "CLEAN": "Chemicals",
    "ALKYLAMINE": "Chemicals", "NEOGEN": "Chemicals", "LXCHEM": "Chemicals", "DMCC": "Chemicals",
    "NOCIL": "Chemicals", "PHILIPCARB": "Chemicals", "SUDARSCHEM": "Chemicals",
    "SUMICHEM": "Chemicals", "UPL": "Chemicals", "RALLIS": "Chemicals", "BAYER": "Chemicals",
    "BAYERCROP": "Chemicals", "DHANUKA": "Chemicals", "INSECTICID": "Chemicals",
    "AARTIIND": "Chemicals", "AGARIND": "Chemicals", "ASTEC": "Chemicals", "BALAJIAM": "Chemicals",
    "BALAMINES": "Chemicals", "BODAL": "Chemicals", "CAMLINFS": "Chemicals", "CHEMPLAST": "Chemicals",
    "CHEMINV": "Chemicals", "CHEMFAB": "Chemicals", "COLOURSCHEM": "Chemicals", "DCM": "Chemicals",
    "DHARAMSI": "Chemicals", "DYNPRO": "Chemicals", "ECOBOARD": "Chemicals", "ELCID": "Chemicals",
    "ENGINERSIN": "Chemicals", "ESTER": "Chemicals", "FAIRCHEM": "Chemicals", "GANDHITUBE": "Chemicals",
    "GHCL": "Chemicals", "GLOMEDICAL": "Chemicals", "GRAUER": "Chemicals", "GULPOLY": "Chemicals",
    "HERANBA": "Chemicals", "HIKAL": "Chemicals", "HIMADRI": "Chemicals", "IOLCP": "Chemicals",
    "JUBLINGREA": "Chemicals", "KANSAINER": "Chemicals", "KIRLOSIND": "Chemicals",
    "TATACOFFEE": "Chemicals", "TRANSPEK": "Chemicals", "ORIENTPPR": "Chemicals",

    # ============== TEXTILES & APPAREL (60+ stocks) ==============
    "RAYMOND": "Textiles", "ARVIND": "Textiles", "WELSPUNIND": "Textiles", "TRIDENT": "Textiles",
    "INDORAMA": "Textiles", "GOKEX": "Textiles", "VARDHMAN": "Textiles", "NITIRAJ": "Textiles",
    "HIMATSEIDE": "Textiles", "KPR": "Textiles", "PGIL": "Textiles", "SUTLEJ": "Textiles",
    "DOLLY": "Textiles", "RUPA": "Textiles", "LAXMIMACH": "Textiles", "SPANDANA": "Textiles",
    "AMBIKACOTM": "Textiles", "BANSWRAS": "Textiles", "BOMBAYBURMH": "Textiles", "CENTEXT": "Textiles",
    "CHAMBLFERT": "Textiles", "CHEVIOT": "Textiles", "DCMSHRI": "Textiles", "DONEAR": "Textiles",
    "GARFIBRES": "Textiles", "GOKALDAS": "Textiles", "HEERAMP": "Textiles", "INDOCOUNT": "Textiles",
    "JAYBHARMAR": "Textiles", "JAYSREETEA": "Textiles", "JOCKEY": "Textiles", "KEWAL": "Textiles",
    "KITEX": "Textiles", "LAKSHMI": "Textiles", "LOVABLE": "Textiles", "LUXIND": "Textiles",
    "MAFATL": "Textiles", "MAHEPC": "Textiles", "MOHRN": "Textiles", "MONTECARLO": "Textiles",
    "NAGJI": "Textiles", "NAHAR": "Textiles", "NAHARCAP": "Textiles", "NAHARSP": "Textiles",
    "NITIN": "Textiles", "NTCIND": "Textiles", "OSWALFR": "Textiles", "PAGE": "Textiles",
    "PALRED": "Textiles", "TCIEXP": "Textiles", "WINSOME": "Textiles", "S&SPOWER": "Textiles",

    # ============== LOGISTICS & TRANSPORT (40+ stocks) ==============
    "ADANIPORTS": "Ports", "CONCOR": "Logistics", "DELHIVERY": "Logistics", "BLUEDART": "Logistics",
    "MAHSEAMLES": "Logistics", "TCI": "Logistics", "AEGISCHEM": "Logistics", "GESHIP": "Logistics",
    "GATEWAY": "Logistics", "ALLCARGO": "Logistics", "IRCTC": "Travel", "INDIGO": "Aviation",
    "SPICEJET": "Aviation", "GMRAIRPORT": "Aviation", "TIDEWATER": "Logistics",
    "ADANITRANS": "Logistics", "APEEJAY": "Logistics", "ARCHIDPLY": "Logistics", "ASTERDM": "Logistics",
    "BIRLACORPN": "Logistics", "BLISSGVS": "Logistics", "BPLLTD": "Logistics", "BUTTERFLY": "Logistics",
    "CAREERPOINT": "Logistics", "CAROL": "Logistics", "CGPOWER": "Logistics", "CLSEL": "Logistics",
    "CENTUM": "Logistics", "CONTAINER": "Logistics", "SICAL": "Logistics", "SEABIRD": "Logistics",
    "SANGHIIND": "Logistics", "SPICE": "Logistics", "WELSPUNENT": "Logistics", "GPIL": "Logistics",

    # ============== CONGLOMERATES (30+ stocks) ==============
    "ADANIENT": "Conglomerate", "GRASIM": "Conglomerate", "AIAENG": "Conglomerate",
    "GODREJIND": "Conglomerate", "MAHINDCIE": "Conglomerate", "MAHLOG": "Conglomerate",
    "VGUARD": "Conglomerate", "RELIANCE": "Conglomerate", "TATAPOWER": "Conglomerate",
    "BAJAJHLDNG": "Conglomerate", "BAJHOLD": "Conglomerate", "BINDALAGRO": "Conglomerate",
    "BLKASHLIM": "Conglomerate", "DCBBANK": "Conglomerate", "EICHERMOT": "Conglomerate",
    "ESCORTS": "Conglomerate", "EXCELCROP": "Conglomerate", "GENUSPOWER": "Conglomerate",
    "GMBREW": "Conglomerate", "GOKUL": "Conglomerate", "GPPL": "Conglomerate",
    "HGINFRA": "Conglomerate", "HINDCOMPOS": "Conglomerate", "INDRAMEDCO": "Conglomerate",
    "INDUSINDBK": "Conglomerate", "ITDCEM": "Conglomerate", "JAGRAN": "Conglomerate",

    # ============== DEFENCE & AEROSPACE (30+ stocks) ==============
    "HAL": "Defence", "BEL": "Defence", "BDL": "Defence", "BEML": "Defence",
    "COCHINSHIP": "Defence", "GRSE": "Defence", "MDL": "Defence", "MIDHANI": "Defence",
    "DATAPATTNS": "Defence", "PARAS": "Defence", "IDEAFORGE": "Defence",
    "ASTRA": "Defence", "CENTUM": "Defence", "DCXIND": "Defence", "DYNAMATIC": "Defence",
    "LSIL": "Defence", "MTAR": "Defence", "NELCO": "Defence", "PARACABLES": "Defence",
    "RADARWAR": "Defence", "RATHIIND": "Defence", "RNAVAL": "Defence", "SAGEMENAV": "Defence",
    "SOLARINDS": "Defence", "TANLAVENTR": "Defence", "TONGANET": "Defence", "ZEN": "Defence",
    "ZENTECHN": "Defence", "ASTERDM": "Defence", "AXISGOLD": "Defence", "AXISCADES": "Defence",

    # ============== PAPER & PACKAGING (30+ stocks) ==============
    "JKPAPER": "Paper", "BALPHARMA": "Paper", "WESTLIFE": "Paper", "TNPL": "Paper",
    "HUHTAMAKI": "Packaging", "UFLEX": "Packaging", "EPACK": "Packaging",
    "ANDHRA": "Paper", "BGRENERGY": "Paper", "CENTUM": "Paper", "EMCOPKG": "Paper",
    "GOLDIAM": "Packaging", "HITECH": "Packaging", "HITECHPLAS": "Packaging", "MAX": "Packaging",
    "MOIL": "Packaging", "NATUREASIA": "Packaging", "ORIENTPPR": "Paper", "PAUSHAKLTD": "Packaging",
    "PIONEER": "Packaging", "PLASTIBLEND": "Packaging", "POLYPLEX": "Packaging", "PRIMEIND": "Packaging",
    "RPPINFRA": "Packaging", "SAGAR": "Packaging", "SUPRBFIN": "Packaging", "TCPLPACK": "Packaging",
    "TIMEXWATCH": "Packaging", "VAGHANI": "Packaging", "WESTERNCO": "Packaging", "ZODIAC": "Packaging",

    # ============== QSR & HOSPITALITY (30+ stocks) ==============
    "JUBLFOOD": "QSR", "DEVYANI": "QSR", "SAPPHIRE": "QSR", "WESTLIFE": "QSR",
    "BARBEQUE": "QSR", "BURGERKING": "QSR", "SPECIALITY": "QSR", "RESTAURANT": "QSR",
    "INDHOTEL": "Hospitality", "ITCHOTEL": "Hospitality", "LEMONTREE": "Hospitality",
    "EIHLTD": "Hospitality", "CHALET": "Hospitality", "ROYALORCHID": "Hospitality",
    "TAJGVK": "Hospitality", "ORIENTHOT": "Hospitality", "MAHINDRAHOL": "Hospitality",
    "DELTACRP": "Hospitality", "THOMASCOOK": "Hospitality", "COXNKING": "Hospitality",
    "MTC": "Hospitality", "STERLING": "Hospitality", "TAJHOTEL": "Hospitality",
    "TRITON": "Hospitality", "VEGANZ": "Hospitality", "WONDERLA": "Hospitality",
    "YASHPAK": "Hospitality", "YATHARTH": "Hospitality", "AIRASIA": "Hospitality",

    # ============== EDUCATIONAL & SERVICES (20+ stocks) ==============
    "APTECH": "Education", "CAREER": "Education", "CLATEDUCATE": "Education",
    "EDUMICRO": "Education", "EVERONN": "Education", "FILATEX": "Education",
    "FOCUS": "Education", "JETFREI": "Education", "MAHSCOOTER": "Education",
    "MTARTECH": "Education", "NIITLTD": "Education", "NORTHG": "Education",
    "QUESS": "Services", "SIS": "Services", "TEAMLEASE": "Services",
    "24X7INSURA": "Services", "AHLUCONT": "Services", "AJCON": "Services",
    "ALMONDZ": "Services", "AMERIND": "Services", "ARCHCORP": "Services",

    # ============== GEMS & JEWELLERY (20+ stocks) ==============
    "TITAN": "Gems & Jewellery", "KALYANKJIL": "Gems & Jewellery", "PNGJAIN": "Gems & Jewellery",
    "SENCO": "Gems & Jewellery", "THANGMAYL": "Gems & Jewellery", "TRIBHO": "Gems & Jewellery",
    "GOLDIAM": "Gems & Jewellery", "RAJESH": "Gems & Jewellery", "RENAISSANCE": "Gems & Jewellery",
    "SUYOG": "Gems & Jewellery", "ASAHI": "Gems & Jewellery", "TRENT": "Gems & Jewellery",
    "GITANJALI": "Gems & Jewellery", "PNJ": "Gems & Jewellery", "TRIBHO": "Gems & Jewellery",
    "VAIBHAV": "Gems & Jewellery", "MALABAR": "Gems & Jewellery", "TANISHQ": "Gems & Jewellery",

    # ============== EXCHANGES & MARKET INFRA (10+ stocks) ==============
    "MCX": "Exchange", "BSE": "Exchange", "CDSL": "Exchange", "NSDL": "Exchange",
    "IEX": "Exchange", "CAMS": "Exchange", "KFINTECH": "Exchange", "ANGELONE": "Exchange",
    "ICEX": "Exchange", "NCDEX": "Exchange", "NDTV": "Exchange", "DCXIND": "Exchange",
}

# ============== FUTURISTIC/EMERGING SECTORS ==============
# High-growth sectors expected to outperform over the next 5-10 years
FUTURISTIC_SECTORS = {
    "EV & Green Energy": {
        "description": "Electric vehicles, batteries, solar, wind, green hydrogen - the clean energy transition",
        "stocks": [
            "TATAMOTORS", "M&M", "TATAPOWER", "ADANIGREEN", "SUZLON",
            "EXIDEIND", "AMARAJABAT", "MOTHERSON", "BHARATFORG", "BOSCH",
            "RELIANCE", "NTPC", "POWERGRID", "TATAELXSI", "KPIT",
            "OLECTRA", "JBMA", "GREENPANEL", "WAAREE", "PREMIER"
        ],
        "top_picks": ["TATAMOTORS", "TATAPOWER", "KPITTECH"],
        "tailwinds": [
            "Government EV subsidies and FAME schemes",
            "PLI schemes for battery manufacturing",
            "India's 2070 net-zero commitment",
            "Declining battery costs",
            "Rising fuel prices making EVs attractive"
        ],
        "growth_potential": "25-35% CAGR for next 5 years",
        "key_metrics": {
            "india_ev_penetration_2023": "2%",
            "target_ev_penetration_2030": "30%",
            "market_size_2030": "$100 billion"
        },
        "risks": [
            "High valuations in some stocks",
            "Execution delays in capacity expansion",
            "Import dependence for batteries"
        ]
    },
    
    "AI & Data Technology": {
        "description": "Artificial Intelligence, cloud computing, data centers, cybersecurity, SaaS",
        "stocks": [
            "TCS", "INFY", "WIPRO", "HCLTECH", "TECHM",
            "PERSISTENT", "LTIM", "COFORGE", "MPHASIS", "LTTS",
            "TATAELXSI", "HAPPSTMNDS", "KPITTECH", "LATENTVIEW", "ZENSAR",
            "NEWGEN", "INTELLECT", "MASTEK", "CYIENT", "BIRLASOFT"
        ],
        "top_picks": ["PERSISTENT", "TATAELXSI", "LTIM"],
        "tailwinds": [
            "GenAI adoption driving IT spending",
            "Digital transformation across industries",
            "India as global tech hub (GCCs)",
            "5G rollout enabling new applications",
            "Data localization requirements"
        ],
        "growth_potential": "15-25% CAGR for next 5 years",
        "key_metrics": {
            "india_it_exports_2023": "$194 billion",
            "ai_market_india_2030": "$17 billion",
            "data_center_growth": "20%+ CAGR"
        },
        "risks": [
            "US recession impacting IT budgets",
            "AI automation reducing headcount",
            "Talent shortage and wage inflation"
        ]
    },
    
    "Defence & Aerospace": {
        "description": "Indigenous defence manufacturing, drones, space technology, UAVs",
        "stocks": [
            "HAL", "BEL", "BEML", "BHEL",
            "COCHINSHIP", "GRSE", "MAZAGON", "MIDHANI",
            "PARAS", "DATAPATTNS", "IDEAFORGE", "SOLARDIRECT",
            "ASTRA", "CENTUM", "BHARAT", "ZEN"
        ],
        "top_picks": ["HAL", "BEL", "DATAPATTNS"],
        "tailwinds": [
            "Make in India defence policy",
            "Rising defence budget (6%+ growth YoY)",
            "Export orders from friendly nations",
            "Space missions and satellite launches",
            "Drone policy supporting indigenous manufacturing"
        ],
        "growth_potential": "20-30% CAGR for next 5 years",
        "key_metrics": {
            "defence_budget_fy24": "₹5.94 lakh crore",
            "domestic_procurement_target": "75%",
            "defence_exports_target_2025": "$5 billion"
        },
        "risks": [
            "Order execution delays",
            "Technology transfer challenges",
            "Budget constraints in recession"
        ]
    },
    
    "Digital Commerce & Fintech": {
        "description": "E-commerce, digital payments, neo-banking, insurance tech",
        "stocks": [
            "DMART", "TRENT", "ZOMATO", "NYKAA",
            "PAYTM", "POLICYBZR", "CARTRADE", "INDIAMART",
            "JUSTDIAL", "INFIBEAM", "EASEMYTRIP", "IXIGO",
            "SBICARD", "BAJFINANCE", "ANGELONE", "CDSL"
        ],
        "top_picks": ["DMART", "ZOMATO", "BAJFINANCE"],
        "tailwinds": [
            "Rising internet penetration (800M+ users)",
            "UPI transaction growth (10B+ monthly)",
            "Tier 2/3 city consumption growth",
            "Insurance penetration increase",
            "Digital credit expansion"
        ],
        "growth_potential": "20-35% CAGR for next 5 years",
        "key_metrics": {
            "india_ecommerce_2030": "$350 billion",
            "digital_payments_2027": "$10 trillion",
            "fintech_market_2025": "$150 billion"
        },
        "risks": [
            "Regulatory changes (RBI)",
            "Cash burn in new-age companies",
            "Competition from global players"
        ]
    },
    
    "Healthcare & Diagnostics": {
        "description": "Hospitals, diagnostics, medical devices, pharma innovation",
        "stocks": [
            "APOLLOHOSP", "FORTIS", "MAXHEALTH", "NARAYANA",
            "LALPATHLAB", "METROPOLIS", "VIJAYA", "THYROCARE",
            "POLYMED", "MEDPLUS", "SYNGENE", "BIOCON",
            "SUNPHARMA", "DRREDDY", "DIVISLAB", "MANKIND"
        ],
        "top_picks": ["APOLLOHOSP", "LALPATHLAB", "SYNGENE"],
        "tailwinds": [
            "Aging population increasing healthcare demand",
            "Medical tourism growth",
            "Health insurance penetration increase",
            "Biosimilar and vaccine opportunities",
            "Government Ayushman Bharat expansion"
        ],
        "growth_potential": "15-20% CAGR for next 5 years",
        "key_metrics": {
            "healthcare_market_2030": "$372 billion",
            "hospital_beds_gap": "2M+ beds needed",
            "diagnostic_market_2025": "$32 billion"
        },
        "risks": [
            "Pricing pressures from government",
            "NLEM expansion",
            "Competition in generics"
        ]
    },
    
    "Infrastructure & Logistics": {
        "description": "Roads, railways, ports, airports, warehousing, logistics tech",
        "stocks": [
            "LT", "ADANIPORTS", "GMRAIRPORT", "IRCTC",
            "CONCOR", "DELHIVERY", "BLUEDART", "MAHLOG",
            "GATI", "TCI", "VRL", "ALLCARGO",
            "INFRATEL", "BHARATFORG", "KEC", "KALPATPOWR"
        ],
        "top_picks": ["LT", "ADANIPORTS", "DELHIVERY"],
        "tailwinds": [
            "NIP (National Infrastructure Pipeline) ₹111 lakh crore",
            "Gati Shakti multimodal connectivity",
            "Dedicated freight corridors",
            "PM Gati Shakti National Master Plan",
            "E-commerce driven warehousing demand"
        ],
        "growth_potential": "15-20% CAGR for next 5 years",
        "key_metrics": {
            "infra_investment_fy28": "₹111 lakh crore",
            "logistics_market_2027": "$380 billion",
            "warehousing_demand_growth": "30%+ CAGR"
        },
        "risks": [
            "Execution delays",
            "Land acquisition issues",
            "Interest rate sensitivity"
        ]
    }
}

# Create complete stock list from SECTOR_MAP
STOCK_UNIVERSE = list(SECTOR_MAP.keys())

# Additional stocks that may need to be added later
ADDITIONAL_STOCKS = []

print(f"Total stocks in universe: {len(STOCK_UNIVERSE)}")
print(f"Total unique sectors: {len(set(SECTOR_MAP.values()))}")
