#!/usr/bin/env python3
"""
Fetch complete list of all NSE listed stocks and download their data.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import logging
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.store import Database
from app.config import config
from app.advanced_screener import add_advanced_indicators, run_advanced_screener
from nse_stocks import SECTOR_MAP

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_all_nse_symbols():
    """
    Fetch complete list of all NSE equity symbols.
    Uses NSE's official API.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    all_symbols = set()

    # Method 1: Try NSE's equity stock watch
    try:
        logger.info("Fetching from NSE equity list...")
        session = requests.Session()
        # First hit the main page to get cookies
        session.get("https://www.nseindia.com", headers=headers, timeout=10)

        # Get all equity symbols
        url = "https://www.nseindia.com/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O"
        response = session.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            for item in data.get('data', []):
                symbol = item.get('symbol', '')
                if symbol:
                    all_symbols.add(symbol)
            logger.info(f"Got {len(all_symbols)} F&O symbols from NSE")
    except Exception as e:
        logger.warning(f"Failed to fetch from NSE API: {e}")

    # Method 2: Use a comprehensive pre-built list of NSE symbols
    # This includes all actively traded stocks
    comprehensive_list = [
        # NIFTY 50
        "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "BHARTIARTL", "INFY", "SBIN",
        "ITC", "HINDUNILVR", "LT", "KOTAKBANK", "AXISBANK", "BAJFINANCE", "MARUTI",
        "ASIANPAINT", "HCLTECH", "SUNPHARMA", "TITAN", "NTPC", "ONGC",
        "TATAMOTORS", "POWERGRID", "M&M", "ULTRACEMCO", "ADANIENT", "ADANIPORTS",
        "BAJAJFINSV", "WIPRO", "JSWSTEEL", "TATASTEEL", "COALINDIA", "NESTLEIND",
        "GRASIM", "BRITANNIA", "HINDALCO", "TECHM", "DIVISLAB", "DRREDDY",
        "CIPLA", "EICHERMOT", "BPCL", "TATACONSUM", "APOLLOHOSP", "INDUSINDBK",
        "SBILIFE", "HDFCLIFE", "BAJAJ-AUTO", "HEROMOTOCO", "VEDL", "ADANIGREEN",

        # NIFTY NEXT 50
        "GODREJCP", "DABUR", "MARICO", "PIDILITIND", "BERGEPAINT", "HAVELLS",
        "SIEMENS", "ABB", "CUMMINSIND", "VOLTAS", "CROMPTON", "POLYCAB",
        "DLF", "GODREJPROP", "OBEROIRLTY", "PRESTIGE", "SOBHA", "PHOENIXLTD",
        "TORNTPHARM", "AUROPHARMA", "BIOCON", "LAURUSLABS", "ALKEM", "LUPIN",
        "ZYDUSLIFE", "MANKIND", "NAUKRI", "DMART", "TRENT", "ABFRL",
        "COLPAL", "PAGEIND", "JUBLFOOD", "MCDOWELL-N", "UBL", "VBL",
        "NHPC", "SJVN", "TATAPOWER", "RECLTD", "PFC", "IRFC",
        "INDIGO", "IRCTC", "CONCOR", "BHARATFORG", "MOTHERSON",

        # NIFTY MIDCAP 150
        "PERSISTENT", "COFORGE", "MPHASIS", "LTIM", "LTTS", "KPITTECH",
        "TATAELXSI", "HAPPSTMNDS", "LATENTVIEW", "TANLA", "ROUTE",
        "CHOLAFIN", "MUTHOOTFIN", "MANAPPURAM", "LICHSGFIN", "SHRIRAMFIN",
        "AUBANK", "IDFCFIRSTB", "FEDERALBNK", "BANDHANBNK", "RBLBANK",
        "PNB", "CANBK", "BANKBARODA", "UNIONBANK", "INDIANB", "IOB",
        "RAMCOCEM", "DALMIACEM", "JKCEMENT", "BIRLACORPN", "INDIACEM",
        "ACC", "AMBUJACEM", "SHREECEM", "NUVOCO",
        "JINDALSTEL", "NMDC", "SAIL", "NATIONALUM", "HINDZINC", "MOIL",
        "PETRONET", "IGL", "MGL", "GAIL", "OIL", "MRPL",
        "SRF", "PIIND", "ATUL", "NAVINFLUOR", "DEEPAKNTR", "TATACHEM",
        "COROMANDEL", "UPL", "RALLIS", "GNFC", "GSFC", "CHAMBALFERT",
        "EXIDEIND", "AMARAJABAT", "BOSCHLTD", "MRF", "BALKRISIND", "APOLLOTYRE",
        "CEATLTD", "SUNDRMFAST", "SCHAEFFLER", "TIMKEN", "SKFINDIA",
        "ESCORTS", "ASHOKLEY", "TVSMOTOR", "FORCEMOT",
        "HAL", "BEL", "BDL", "BEML", "COCHINSHIP", "GRSE", "MDL",
        "RVNL", "IRCON", "RITES", "ENGINERSIN", "NBCC", "NCC",
        "MCX", "BSE", "CDSL", "CAMS", "KFINTECH", "ANGELONE",
        "ZOMATO", "PAYTM", "NYKAA", "POLICYBZR",
        "LICI", "GICRE", "NIACL", "STAR", "ICICIGI", "ICICIPRULI",
        "MAXHEALTH", "FORTIS", "MEDANTA", "KIMS",
        "LALPATHLAB", "METROPOLIS",
        "DIXON", "AMBER", "KALYANKJIL",
        "BLUEDART", "DELHIVERY", "ALLCARGO", "TCI",
        "SUNTV", "ZEEL", "PVR", "SAREGAMA", "NAZARA",
        "BHARTIARTL", "IDEA", "TATACOMM", "INDUSTOWER",
        "DEVYANI", "WESTLIFE",

        # NIFTY SMALLCAP 250 - Popular ones
        "GRINDWELL", "CARBORUNIV", "HEG", "GRAPHITE", "AIAENG",
        "JKPAPER", "TNPL", "UFLEX",
        "WELCORP", "RATNAMANI", "APLAPOLLO", "JINDALSAW",
        "DCBBANK", "KARURVYSYA", "CITYUNIONB", "SOUTHBANK", "JKBANK",
        "EQUITASBNK", "UJJIVANSFB", "CREDITACC", "APTUS", "AAVAS", "HOMEFIRST",
        "NATCOPHARMA", "GRANULES", "GLENMARK", "IPCA", "ABBOTINDIA",
        "PFIZER", "GLAXO", "SANOFI", "JBPHARMA", "AJANTPHARM", "ERIS",
        "NIITLTD", "CYIENT", "SONATSOFTW", "NEWGEN", "INTELLECT", "MASTEK",
        "ECLERX", "ZENSAR", "BIRLASOFT", "RATEGAIN", "DATAPATTNS",
        "ENDURANCE", "SUPRAJIT", "GABRIEL", "UNOMINDA",
        "ELGIEQUIP", "TRIVENI", "THERMAX", "KALPATPOWR", "KEC",
        "ORIENTELEC", "BAJAJELEC", "SYMPHONY", "BLUESTARCO", "WHIRLPOOL",
        "RADICO", "BAJAJCON", "EMAMILTD", "JYOTHYLABS",
        "HATSUN", "BIKAJI",
        "RELAXO", "BATAINDIA", "VMART", "SHOPERSTOP",
        "SUZLON", "INOXWIND",
        "MAPMYINDIA", "AFFLE", "INDIAMART", "JUSTDIAL",
        "MOTILALOFS", "EDELWEISS", "IIFL",
        "HUDCO", "CRISIL",
        "JSWENERGY", "CESC", "TORNTPOWER", "NLCINDIA",
        "RCF", "NFL",
        "FINEORG", "VINATIORGA", "GALAXYSURF", "AARTIIND",
        "ALKYLAMINE", "NOCIL", "SUDARSCHEM",
        "SUMICHEM",
        "KNRCON", "ASHOKA", "PNCINFRA", "HGINFRA", "IRB",
        "BRIGADE", "MAHLIFE", "LODHA", "SUNTECK",
        "KEI", "FINOLEX",
        "ASTRAL", "SUPREMEIND", "CENTURYPLY", "GREENPANEL",
        "KAJARIACER", "SOMANYCERA",
        "RAYMOND", "ARVIND", "WELSPUNIND", "TRIDENT", "KPR",
        "OLECTRA",

        # Additional Small & Micro caps (commonly traded)
        "INOXGREEN", "WAAREE", "PREMIERENE", "ADANIPOWER", "ASAHIINDIA",
        "AARTIDRUGS", "AARTISURF", "AAVAS", "ABSLAMC", "ACCELYA",
        "ACE", "ADANIENSOL", "ADVENZYMES", "AEGISLOG", "AETHER",
        "AFFLE", "AGARIND", "AGROPHOS", "AHLUCONT", "AIAENG",
        "AIRAN", "AJMERA", "AKZOINDIA", "ALEMBICLTD", "ALEXANDER",
        "ALFREDHER", "ALLSEC", "ALMONDZ", "ALOKTEXT", "AMIORG",
        "ANANTRAJ", "ANDHRABANK", "ANDHRSUGAR", "ANGELONE", "ANIKINDS",
        "ANTGRAPHIC", "APARINDS", "APCL", "APCOTEXIND", "APEX",
        "APLAPOLLO", "APLLTD", "APOLLO", "APOLLOHOSP", "APOLLOPIPE",
        "APOLLOTYRE", "APTECHT", "ARCHIDPLY", "ARCHIES", "ARIHANT",
        "ARIHANTSUP", "ARSHIYA", "ARTEMISMED", "ARVINDFASN", "ARVIND",
        "ASAHIINDIA", "ASAHISONG", "ASHAPURMIN", "ASHIANA", "ASHOKA",
        "ASIANHOTNR", "ASIANPAINT", "ASPINWALL", "ASTEC", "ASTERDM",
        "ASTRAL", "ASTRAZEN", "ATALREAL", "ATFL", "ATLANTA",
        "ATLASCYCLE", "ATNINTER", "ATUL", "AURIONPRO", "AUROPHARM",
        "AUROPHARMA", "AURUM", "AUTHUM", "AUTOAXLES", "AUTOLITIND",
        "AVADHSUGAR", "AVANTIFEED", "AWHCL", "AXISBANK", "AXISCADES",
        "AYMSYNTEX", "AZAD", "BAFNAPH", "BAGFILMS", "BAJAJ-AUTO",
        "BAJAJELEC", "BAJAJFINSV", "BAJAJHIND", "BAJAJHLDNG", "BAJFINANCE",
        "BALAJITELE", "BALAMINES", "BALKRISHNA", "BALKRISIND", "BALLARPUR",
        "BALMLAWRIE", "BALPHARMA", "BALRAMCHIN", "BANARBEADS", "BANCOINDIA",
        "BANDHANBNK", "BANKBARODA", "BANKINDIA", "BASF", "BASML",
        "BATAINDIA", "BAYERCROP", "BBL", "BBTC", "BDL",
        "BEARDSELL", "BECTORFOOD", "BEDMUTHA", "BEL", "BEML",
        "BENGALASM", "BERGEPAINT", "BFINVEST", "BFUTILITIE", "BGRENERGY",
        "BHAGERIA", "BHAGYANGR", "BHAGYNAGAR", "BHARATFORG", "BHARATGEAR",
        "BHARATRAS", "BHARATWIRE", "BHARTIARTL", "BHEL", "BIL",
        "BIKAJI", "BIRLACABLE", "BIRLACORPN", "BIRLAMONEY", "BLBLIMITED",
        "BLISSGVS", "BLKASHYAP", "BLUECHIP", "BLUEDART", "BLUESTARCO",
        "BODALCHEM", "BOMDYEING", "BORORENEW", "BOSCHLTD", "BPCL",
        "BPL", "BRFL", "BRIGADE", "BRITANNIA", "BRNL",
        "BROOKS", "BSE", "BSHSL", "BURNPUR", "BUTTERFLY",
        "BVCL", "BYKE", "CALCOMP", "CAMLINFINE", "CAMPUS",
        "CAMS", "CANBK", "CANFINHOME", "CANTABIL", "CAPACITE",
        "CAPLIPOINT", "CAPTRUST", "CARBORUNIV", "CARERATING", "CARYSIL",
        "CASTROLIND", "CCL", "CDSL", "CEATLTD", "CELEBRITY",
        "CENTENKA", "CENTRALBK", "CENTRUM", "CENTUM", "CENTURYPLY",
        "CENTURYTEX", "CERA", "CEREBRAINT", "CESC", "CGCL",
        "CGPOWER", "CHALET", "CHAMBLFERT", "CHEMPLASTS", "CHENNPETRO",
        "CHOLAFIN", "CHOLAHLDNG", "CHROMATIC", "CIGNITI", "CINELINE",
        "CIPLA", "CLSEL", "CMSINFO", "COALINDIA", "COCHINSHIP",
        "COFFEEDAY", "COFORGE", "COLPAL", "COMPINFO", "COMPUAGE",
        "CONCOR", "CONFIPET", "CONTROLPR", "COPRAN", "CORALFINAC",
        "CORDSCABLE", "COROMANDEL", "COSMOFILMS", "COUNCODOS", "COX&KINGS",
        "CPCL", "CREATIVEYE", "CREDITACC", "CREST", "CRISIL",
        "CROMPTON", "CSBBANK", "CUB", "CUMMINSIND", "CUPID",
        "CYBERTECH", "CYIENT", "DABUR", "DALMIASUG", "DATAMATICS",
        "DATAPATTNS", "DBCORP", "DBL", "DBREALTY", "DCAL",
        "DCBBANK", "DCMSHRIRAM", "DCMNVL", "DCW", "DEEPAKFERT",
        "DEEPAKNTR", "DEEPIND", "DELTACORP", "DELTAMAGNT", "DEN",
        "DEVYANI", "DGCONTENT", "DHAMPURSUG", "DHANBANK", "DHANI",
        "DHANUKA", "DHFL", "DHUNINV", "DIAMONDYD", "DICIND",
        "DIENSTEN", "DIGICONTENT", "DIGJAMLTD", "DIOLIVE", "DISHTV",
        "DIVISLAB", "DIXON", "DLF", "DLINKINDIA", "DMART",
        "DOLLAR", "DOLLEX", "DPSCLTD", "DQE", "DREDGECORP",
        "DRREDDY", "DUNCANSLTD", "DUPONTIND", "DWARIKESH", "DWARKESH",
        "DYNAMATECH", "DYNPRO", "EASEMYTRIP", "EBBETF0425", "EBBETF0430",
        "EBBETF0431", "ECLERX", "EDELWEISS", "EDUCOMP", "EIDPARRY",
        "EIFFL", "EIHAHOTELS", "EIHOTEL", "EIMCOELECO", "EKC",
        "ELECON", "ELECTCAST", "ELECTHERM", "ELGIEQUIP", "ELGIRUBCO",
        "EMAMILTD", "EMCO", "EMKAY", "EMMBI", "EMUDHRA",
        "ENDURANCE", "ENERGYDEV", "ENGINERSIN", "ENIL", "ENTERTAINMENT",
        "EON", "EPIGRAL", "EPL", "EQUIPPP", "ERIS",
        "EROSMEDIA", "ESABINDIA", "ESCORTS", "ESSARSHPNG", "ESTER",
        "ETHOSLTD", "EUROTEXIND", "EVEREADY", "EVERESTIND", "EXCEL",
        "EXCELCROP", "EXCELIND", "EXIDEIND", "EXPLEOSOL", "FACT",
        "FAIRCHEM", "FAZE3Q", "FCL", "FCSSOFT", "FDCLTD",
        "FEDERALBNK", "FEL", "FEML", "FGPL", "FIEMIND",
        "FILATFASH", "FILATEX", "FINCABLES", "FINPIPE", "FIRSTCRY",
        "FIVESTAR", "FLEXITUFF", "FLFL", "FLUOROCHEM", "FMGOETZE",
        "FMNL", "FMTL", "FOKUS", "FOODSIN", "FORCEMOT",
        "FORTIS", "FOSECOIND", "FRETAIL", "FSL", "GABRIEL",
        "GAIL", "GALAXYSURF", "GALLANTTIS", "GANDHAR", "GANESHBE",
        "GANESHHOU", "GANGAFORGE", "GANGESFORG", "GANECOS", "GARDENSILK",
        "GARFIBRES", "GATEWAY", "GAYAPROJ", "GCPL", "GDL",
        "GEECEE", "GEEKAYWIRE", "GEINDSYS", "GENCON", "GENESYS",
        "GENSOL", "GENUSPAPER", "GENUSPOWER", "GEOMETRIC", "GESHIP",
        "GET&D", "GFLLIMITED", "GHCL", "GICHSGFIN", "GICRE",
        "GILETTE", "GILLANDERS", "GILLETTE", "GIPCL", "GKWLIMITED",
        "GLAND", "GLAXO", "GLENMARK", "GLFL", "GLOBALVECT",
        "GLOBOFFS", "GLOBUSSPR", "GLS", "GMMPFAUDLR", "GMRINFRA",
        "GNA", "GNFC", "GOACARBON", "GOCLCORP", "GOCOLORS",
        "GODAWARI", "GODFRYPHLP", "GODREJAGRO", "GODREJCP", "GODREJIND",
        "GODREJPROP", "GOENKA", "GOKALDAS", "GOKUL", "GOKULAGRO",
        "GOLDENTOBC", "GOLDIAM", "GOLDTECH", "GOODLUCK", "GOODYEAR",
        "GPIL", "GPPL", "GPTINFRA", "GRANULES", "GRAPHITE",
        "GRASIM", "GRAVITA", "GRMOVER", "GREENINFRA", "GREENPANEL",
        "GREENPLY", "GREAVESCOT", "GREENLAM", "GREENPOWER", "GRINDWELL",
        "GROBTEA", "GRPLTD", "GRSE", "GSFC", "GSKCONS",
        "GSPL", "GTNIND", "GTNTEX", "GTL", "GTLINFRA",
        "GUFICBIO", "GUJALKALI", "GUJAPOLLO", "GUJGASLTD", "GUJNRECOKE",
        "GUJRAFFIA", "GULFOILLUB", "GULPOLY", "GVKPIL", "HARRMALAYA",
        "HATHWAY", "HATSUN", "HAVELLS", "HAWAENG", "HAWKINCOOK",
        "HBLPOWER", "HCLTECH", "HDFC", "HDFCAMC", "HDFCBANK",
        "HDFCLIFE", "HEG", "HEIDELBERG", "HEMIPROP", "HERANBA",
        "HERCULES", "HERITGFOOD", "HEROMOTOCO", "HESTERBIO", "HEXAWARE",
        "HFCL", "HGS", "HIKAL", "HIL", "HILTON",
        "HIMATSEIDE", "HINDALCO", "HINDCOMPOS", "HINDCOPPER", "HINDDASI",
        "HINDMOTORS", "HINDNATGLS", "HINDOILEXP", "HINDPETRO", "HINDUNILVR",
        "HINDWAREAP", "HINDZINC", "HIRECT", "HISARMETAL", "HITECH",
        "HITECHGEAR", "HITECHCORP", "HLE", "HMA", "HMVL",
        "HNDFDS", "HNGSNGBEES", "HOMEFIRST", "HONDAPOWER", "HONAUT",
        "HPL", "HSCL", "HTMEDIA", "HUBTOWN", "HUDCO",
        "HUHTAMAKI", "ICICIBANK", "ICICIGI", "ICICIPRULI", "ICIL",
        "ICRA", "IDBI", "IDEA", "IDFC", "IDFCFIRSTB",
        "IEX", "IFBAGRO", "IFBIND", "IFCI", "IFGLEXPOR",
        "IFL", "IGARASHI", "IGATRADE", "IGL", "IIFL",
        "IIFLSEC", "IIFLWAM", "IIP", "IKIO", "IL&FSENGG",
        "IL&FSTRANS", "IMAGICAA", "IMFA", "IMMIGRANT", "IMPEXFERRO",
        "INCREDIBLE", "INDBANK", "INDHOTEL", "INDIACEM", "INDIAGLYCO",
        "INDIAMART", "INDIANB", "INDIANCARD", "INDIANHUME", "INDIGO",
        "INDNIPPON", "INDOAMINES", "INDOBORAX", "INDOCO", "INDORAMA",
        "INDOSTAR", "INDOTECH", "INDOWIND", "INDRAMEDCO", "INDSWFTLAB",
        "INDSWFTLTD", "INDTERRAIN", "INDUSINDBK", "INDUSTOWER", "INEOSSTYRO",
        "INFINITE", "INFIBEAM", "INFY", "INGERRAND", "INNOIND",
        "INOXGREEN", "INOXLEISUR", "INOXWIND", "INSECTICID", "INSPIRISYS",
        "INTELLECT", "INTENTTECH", "INTLCONVYR", "INVENTURE", "IOLCP",
        "IONEXCHANG", "IPCALAB", "IPL", "IRB", "IRCON",
        "IRCTC", "IRFC", "IRIS", "ISEC", "ISFT",
        "ISGEC", "ISMTLTD", "ITC", "ITDC", "ITDCEM",
        "ITI", "ITUL", "IVC", "IVP", "IWEL",
        "IZMO", "J&KBANK", "JAGRAN", "JAGSNPHARM", "JAIBALAJI",
        "JAICORPLTD", "JAINEX", "JAINAM", "JAJOO", "JAKELE",
        "JAMDIST", "JAMNAAUTO", "JASH", "JASMINEINF", "JAYAGROGN",
        "JAYNECOIND", "JAYSREETEA", "JAYWDPOLY", "JBCHEPHARM", "JBFIND",
        "JBMA", "JCHAC", "JDPOWER", "JETAIRWAYS", "JETFREIGHT",
        "JFLLIFE", "JGCHEM", "JINDALPOLY", "JINDALPHOT", "JINDALSAW",
        "JINDALSTEL", "JINDWORLD", "JISLJALEQS", "JITFINFRA", "JIYAECO",
        "JKCEMENT", "JKIL", "JKLAKSHMI", "JKPAPER", "JKTYRE",
        "JLL", "JLMACRO", "JMFINANCIL", "JMTAUTOLTD", "JOCIL",
        "JPASSOCIAT", "JPINFRATEC", "JPPOWER", "JPOLYINVST", "JSL",
        "JSLHISAR", "JSWENERGY", "JSWHL", "JSWSTEEL", "JTEKTINDIA",
        "JUBILANT", "JUBLFOOD", "JULIEN", "JUSTDIAL", "JYOTHYLAB",
        "JYOTISTRUC", "KABRAEXTRU", "KAJARIACER", "KAKATCEM", "KALPATPOWR",
        "KALYANKJIL", "KAMATHOTEL", "KAMDHENU", "KANANIIND", "KANORICHEM",
        "KANSAINER", "KAPSTON", "KARMAENG", "KARNATKNBK", "KARURVYSYA",
        "KASHIPOW", "KAYNES", "KCP", "KCPSUGIND", "KEC",
        "KECL", "KEI", "KELLTONTEC", "KENNAMET", "KERNEX",
        "KESORAMIND", "KHAITAN", "KHANDSE", "KICL", "KILITCH",
        "KIMS", "KINGFA", "KIOCL", "KIRIINDO", "KIRLFER",
        "KIRLOSENG", "KIRLOSIND", "KIRLPNU", "KITEX", "KNRCON",
        "KOHINOOR", "KOKUYOCMLN", "KOLTEPATIL", "KOPRAN", "KOTAKBANK",
        "KOTARISUG", "KOTHARICORP", "KPITTECH", "KPR", "KPRMILL",
        "KRBL", "KREDENT", "KRITI", "KROSS", "KRSNA",
        "KSB", "KSCL", "KSERV", "KSL", "KTKBANK",
        "KUTCHI", "L&TFH", "LAKPRE", "LALPATHLAB", "LAMBODHARA",
        "LANDMARK", "LAOPALA", "LATENTVIEW", "LAURUSLABS", "LAXMIMACH",
        "LGBBROSLTD", "LGBFORGE", "LICI", "LIBERTSHOE", "LIKHITHA",
        "LINCOLN", "LINDEINDIA", "LLOYDS", "LLOYDSME", "LODHA",
        "LOKESHMAC", "LORENZPHAR", "LOTUSEYE", "LOVABLETRD", "LSIL",
        "LT", "LTFOODS", "LTIM", "LTINFRA", "LTL",
        "LTTS", "LUMAXIND", "LUMAXTECH", "LUNAR", "LUPINLTD",
        "LUXIND", "LXCHEM", "LYKALABS", "M&M", "M&MFIN",
        "MAANALU", "MADHAV", "MADRASFERT", "MADYACEM", "MAGMA",
        "MAHABANK", "MAHAPEXLTD", "MAHARSHIHO", "MAHALOG", "MAHAPROP",
        "MAHESHWARI", "MAHINDCIE", "MAHLIFE", "MAHLOG", "MAHSEAMLES",
        "MAITHANALL", "MAJESCO", "MALOTH", "MANAKALUCO", "MANAKCOAT",
        "MANAKSIA", "MANAKSTEEL", "MANAPPURAM", "MANDHANA", "MANGALAM",
        "MANGCHEFER", "MANGLMCEM", "MANGLOIL", "MANGTIMBER", "MANIIND",
        "MANINFRA", "MANKIND", "MANOMAY", "MANORAMA", "MANORG",
        "MANPASAND", "MAPMYINDIA", "MAPSKO", "MARATHON", "MARICO",
        "MARKSANS", "MARSHALL", "MARSSTEEL", "MARUTI", "MASFIN",
        "MASKINVEST", "MASTEK", "MATRIMONY", "MAWANASUG", "MAXFINANCE",
        "MAXHEALTH", "MAXIND", "MAXVIL", "MAYURUNIQ", "MAZAGON",
        "MBAPL", "MBLINFRA", "MCDOWELL-N", "MCLEODEXPO", "MCLEODRUSSA",
        "MCX", "MDL", "MEDANTA", "MEDICAMEN", "MEDPLUS",
        "MEGHMANI", "MEGH", "MHRIL", "MIDHANI", "MIRCELECTR",
        "MIRZAINT", "MISHTANN", "MITTAL", "MMFL", "MMP",
        "MMTC", "MODISONLTD", "MODIRUBBER", "MOHITIND", "MOHENINDIA",
        "MOIL", "MOLDTECH", "MOLDTKPAC", "MONDIFILE", "MONEYWISE",
        "MOOSLBSE", "MORARJEE", "MOREPENLAB", "MOTHERSON", "MOTILALOFS",
        "MOTOGENFIN", "MOTOROLIND", "MPHASIS", "MPSLTD", "MRF",
        "MRO-TEK", "MRPL", "MSKSEC", "MSTCLTD", "MTARTECH",
        "MTEDUCARE", "MTNL", "MUKANDLTD", "MUKATPIPE", "MULTIFIN",
        "MUNJALSHOW", "MUNOTALINE", "MURUDCERA", "MUTHOOTCAP", "MUTHOOTFIN",
        "NACLIND", "NAGAFERT", "NAGREEKCAP", "NAGREEKEXP", "NAKODA",
        "NALCO", "NALINLEASE", "NAM-INDIA", "NANDAN", "NARAYANRUD",
        "NARENDRAPB", "NARMADA", "NATCOPHARM", "NATIONALUM", "NATHBIOGEN",
        "NAUKRI", "NAVINFLUOR", "NAVKARIND", "NAVKARCORP", "NAVNETEDUL",
        "NAZARA", "NBA", "NBCC", "NBIFIN", "NCC",
        "NDA", "NDGL", "NDRAUTO", "NDTV", "NECTAR",
        "NEILIND", "NELCAST", "NELCO", "NESCO", "NESTLEIND",
        "NETFBEES", "NETWORK18", "NEWGEN", "NEXTMEDIA", "NFL",
        "NH", "NHPC", "NIACL", "NIBL", "NICCHEMIN",
        "NIITLTD", "NIITTECH", "NILAINFRA", "NILKAMAL", "NINJAINDEX",
        "NIPPONLIFE", "NITCO", "NITINSPIN", "NITIRAJ", "NITTAGELA",
        "NKIND", "NLCINDIA", "NMDC", "NOCIL", "NOIDATOLL",
        "NOVARTIND", "NPBET", "NRBBEARING", "NSIL", "NSLNISP",
        "NTPC", "NUCENT", "NUCLEUS", "NUVOCO", "NYKAA",
        "OBEROI", "OBEROIRLTY", "OCCL", "OIL", "OILCOUNTUB",
        "OLECTRA", "OMAXAUTO", "OMAXE", "OMANSH", "OMMETALE",
        "ONELIFECAP", "ONEPOINT", "ONGC", "ONMOBILE", "OPAL",
        "OPTIMUS", "OPTOCIRCUI", "ORBTEXP", "ORCHIDPHAR", "ORIANA",
        "ORIENTABRA", "ORIENTBELL", "ORIENTCEM", "ORIENTELEC", "ORIENTHOT",
        "ORIENTLTD", "ORIENTPPR", "ORIENTREA", "ORISSAMINE", "ORTEL",
        "OSWALAGRO", "OSWALGREEN", "OTCPHARMA", "PAGEINDS", "PAGEIND",
        "PAISALO", "PANACHE", "PANAMAPET", "PANASONIC", "PANSARI",
        "PANYAM", "PAPERPROD", "PARABDRUGS", "PARACABLES", "PARAGON",
        "PARAM", "PARAMESU", "PARAS", "PARASHRAM", "PARRYSUGAR",
        "PARSVNATH", "PARTYCRUS", "PATELENG", "PATINTLOG", "PATSPINLTD",
        "PATSPIN", "PAVNAIND", "PAYTM", "PCAYTECH", "PCBLLTD",
        "PCJEWELLER", "PDS", "PDL", "PDMJEPAPER", "PEL",
        "PENIND", "PENPEBS", "PENTASOFT", "PERISTAL", "PERSISTENT",
        "PETRONET", "PFC", "PFIZER", "PGEL", "PGHH",
        "PGHL", "PHILIPCARB", "PHOENIXLTD", "PIDILITIND", "PIERGIS",
        "PIIND", "PILANIINVS", "PIONDIST", "PIONEER", "PITTIENG",
        "PKTEA", "PLASTIBLEN", "PNCINFRA", "PNBGILTS", "PNBHOUSING",
        "PNB", "POCL", "PODDAR", "POKARNALIM", "POKARNA",
        "POLICYBZR", "POLYCAB", "POLYMED", "POLYPLEX", "PONNIERODE",
        "POOJAOIL", "PPL", "PPSINVST", "PRABHAI", "PRACOPAL",
        "PRADIPIND", "PRAJIND", "PRAKASH", "PRAKASHSTL", "PRATAPCHEM",
        "PRATAP FI", "PRECAM", "PRECOT", "PRECWIRE", "PREMEXPLN",
        "PREMIERPOL", "PRESTIGE", "PREVENTIVE", "PRIDE", "PRITIKAUTO",
        "PRITI", "PRIVISCL", "PRIZORFIN", "PRIYANKAENT", "PROINDIA",
        "PRSMOHNSON", "PSPPROJECT", "PTL", "PUNJABCHEM", "PUNJABSIND",
        "PVP", "PVR", "PVRINOX", "QGOLDHALF", "QUASAR",
        "QUESS", "QUICKHEAL", "RADAAN", "RADIOCITY", "RADICO",
        "RAIN", "RAJALAKSH", "RAJESHEXPO", "RAJRATAN", "RAJRILTD",
        "RAJSREESUG", "RAJTNAGAR", "RALLIS", "RAMANEWS", "RAMAPETRO",
        "RAMAPHO", "RAMASIGNS", "RAMCOCEM", "RAMCOIND", "RAMCOSYS",
        "RAMKY", "RAMKYLABIK", "RAMSARUP", "RANASUG", "RANEENGINE",
        "RANEHOLDIN", "RANIKHET", "RATESOFT", "RATHINSP", "RATNAMANI",
        "RATNABHUMI", "RAYMONDLTD", "RAYMOND", "RBA", "RBLBANK",
        "RBM", "RCCL", "RCF", "RECLTD", "REDINGTON",
        "REFLEXIND", "REFNOL", "REGALFINC", "REGENCYCER", "RELAXO",
        "RELIANCE", "RELIGARE", "RELINFRA", "REMSONSIND", "RENUKA",
        "REPCO", "REPCOHOME", "REPRO", "RESPONIND", "REVATHI",
        "RGL", "RHIM", "RICOAUTO", "RIIL", "RILINFRA",
        "RITCO", "RITES", "RKDL", "RKEC", "RKFORGE",
        "ROHLTD", "ROLEXRINGS", "ROLLT", "ROML", "ROSSELL",
        "ROSSELLIND", "ROUTE", "RPGLIFE", "RPGLS", "RPOWER",
        "RPPINFRA", "RSSOFTWARE", "RSYSTEMS", "RSWM", "RTNINDIA",
        "RTNPOWER", "RUCHINFRA", "RUCHIRA", "RUCHISOYA", "RUPA",
        "RUSHIL", "RVNL", "SABTN", "SADBHAV", "SADHNANIQ",
        "SAFARI", "SAGARDEEP", "SAGCEM", "SAH", "SAHANA",
        "SAHMINING", "SAIL", "SAKAR", "SAKSOFT", "SAKUMACHEM",
        "SAKUMA", "SALSTEEL", "SALZERELEC", "SAMBHAAV", "SAMETRANS",
        "SANCO", "SANGHIIND", "SANGHVIMOV", "SANGINITA", "SANGWANITY",
        "SANOFI", "SANWARIA", "SAPPHIRE", "SAREGAMA", "SARLAPERFOR",
        "SASKEN", "SAT", "SATINDLTD", "SATINCRELT", "SATIN",
        "SAVEN", "SAWACA", "SBCL", "SBICARD", "SBILIFE",
        "SBIN", "SBINEQWETF", "SCAPDVR", "SCHAEFFLER", "SCHNEIDER",
        "SCPL", "SDBL", "SEAMECLTD", "SEEDS", "SEIDM",
        "SELMC", "SELPAG", "SELAN", "SENCO", "SEPC",
        "SEQUENT", "SERVALL", "SESHAPAPER", "SETCO", "SETFNIF50",
        "SHADOW", "SHAHALLOY", "SHAILY", "SHAKTIPHARMA", "SHALIMAR",
        "SHALPAINTS", "SHAMBHOST", "SHANKARA", "SHANTIGEAR", "SHARDACROP",
        "SHARDAMOT", "SHAREINDIA", "SHEMAROO", "SHIVAMAUTO", "SHIVAMILLS",
        "SHIVATEX", "SHK", "SHOPERSTOP", "SHRADHA", "SHREECEM",
        "SHREEPUSHK", "SHREERAMA", "SHREYAS", "SHRIRAMCIT", "SHRIRAMFIN",
        "SHRIRAMPPS", "SHYAMTELM", "SIEMENS", "SIGACHI", "SIGIND",
        "SILGO", "SIMBHAGOLD", "SIMPLEXINF", "SIMPLEXCAS", "SINOVEST",
        "SINTEX", "SIRCA", "SIS", "SIS", "SITINET",
        "SJVN", "SKFINDIA", "SKIPPER", "SML", "SMLISUZU",
        "SMSLIFE", "SMSPHARMA", "SNOWMAN", "SOBHA", "SOFCOM",
        "SOLARA", "SOLEX", "SOMANYCERA", "SOMATEX", "SOMANY",
        "SONACOMS", "SONATSOFTW", "SOTL", "SOUTHBANK", "SPAL",
        "SPANDANA", "SPARC", "SPECIALITY", "SPENCERS", "SPIC",
        "SPICEJET", "SPLPETRO", "SPLTECH", "SPORTKING", "SPWL",
        "SQSBFSI", "SREINFRA", "SRESHTA", "SRF", "SRHHYPOLTD",
        "SRICEMENT", "SRTRANSFIN", "SSWL", "STAMPEDE", "STAR",
        "STARCEMENT", "STARPAPER", "STARTECK", "STEELAUTH", "STEELCITY",
        "STEELXIND", "STEL", "STERLINBIO", "STERTOOLS", "STFC",
        "STINDIA", "STLTECH", "STOCKMAVEN", "STOVEKRAFT", "STRTECH",
        "SUBCAPCITY", "SUBEX", "SUBROS", "SUDARSCHEM", "SUJALA",
        "SULA", "SUMEET", "SUMICHEM", "SUMMITSEC", "SUNCLAYLTD",
        "SUNDARAM", "SUNDARMFIN", "SUNDARMHLD", "SUNDRMBRAK", "SUNDRMFAST",
        "SUNFLAG", "SUNGOLD", "SUNILHITEC", "SUNITEC", "SUNPHARMA",
        "SUNTECK", "SUNTV", "SUPERHOUSE", "SUPERPH", "SUPRAJIT",
        "SUPREMEIND", "SUPREMETEX", "SURANASOL", "SURANATELE", "SURANAIND",
        "SURYALAXMI", "SURYAROSNI", "SUTLEJTEX", "SUVENPHAR", "SUVEN",
        "SUZLON", "SVARINFRA", "SVLL", "SWANENERGY", "SWARAJENG",
        "SWSOLAR", "SYMPHONY", "SYNGENE", "SYRMA", "SYTECHCORP",
        "TAJGVK", "TAKE", "TAL", "TALWGYSLL", "TAMILNADU",
        "TANLA", "TARMAT", "TATACHEM", "TATACOMM", "TATACONSUM",
        "TATAELXSI", "TATAINVEST", "TATAMETAL", "TATAMOTORS", "TATAPOWER",
        "TATASTEEL", "TATASTLLP", "TATATECH", "TATVA", "TBZ",
        "TCI", "TCIDEVELOP", "TCIEXPRESS", "TCNSBRANDS", "TCPLPACK",
        "TCS", "TDPOWERSYS", "TEAMLEASE", "TECHINDIA", "TECHM",
        "TECHNOE", "TECILCHEM", "TEMBO", "TEXINFRA", "TEXMOPIPES",
        "TEXRAIL", "TEXTRADE", "TFCILTD", "TGBHOTELS", "THANGABAR",
        "THEJO", "THEMISMED", "THERMAX", "THIRUAROOPA", "THIRUSUGAR",
        "THOMASCOOK", "THOMASCOTT", "THYROCARE", "TI", "TIAAN",
        "TIDEWATER", "TIIL", "TIJARIA", "TII", "TIITAN",
        "TIMETECHNO", "TIMKEN", "TINPLATE", "TIPSFILMS", "TIPSINDLTD",
        "TIRUMALCHM", "TIRUPATGRS", "TITAN", "TMRVL", "TNPETRO",
        "TNPL", "TNTELCOM", "TOLINS", "TOKYOPLAST", "TORNTPHARM",
        "TORNTPOWER", "TOTALTECH", "TPLPLASTEH", "TRACXN", "TRANSIND",
        "TREJHARA", "TRENT", "TRF", "TRIDENT", "TRIGYN",
        "TRIL", "TRITON", "TRIVENI", "TSLGD", "TTK",
        "TTKHEALTH", "TTKPRESTIG", "TTL", "TTLHSC", "TV18BRDCST",
        "TVALABS", "TVSMOTOR", "TVSSRICAKR", "TWL", "UCOBANK",
        "UDPL", "UFLEX", "UFO", "UGARSUGAR", "UJAAS",
        "UJJIVAN", "UJJIVANSFB", "ULTRACEMCO", "UMAEXPORTS", "UMANG",
        "UMESLTD", "UNICHEMLAB", "UNIC", "UNIGEN", "UNIMECH",
        "UNIONBANK", "UNIPLY", "UNIPPLY", "UNITDSPR", "UNITECH",
        "UNITY", "UNIVASTU", "UNIVCABLES", "UNOMINDA", "UPAL",
        "UPL", "UPSURGE", "URJA", "USHAMART", "UTIAMC",
        "UTTAMSTL", "UTTAMSUGAR", "UTI", "UTKARSHBNK", "UVSL",
        "VADILALIND", "VAIBHAVGBL", "VAKRANGEE", "VALORISE", "VALUEIND",
        "VALYUMD", "VAMIKAM", "VARROC", "VARROCENG", "VARUNJAPAN",
        "VASCON", "VASCONEQ", "VASTINFRA", "VBLLTD", "VBL",
        "VEDL", "VEERHEALTH", "VENKEYS", "VENKYS", "VENUSPIPES",
        "VERTOZ", "VESUVIUS", "VETO", "VGUARD", "VHL",
        "VICAT", "VIDEOIND", "VIPCLOTHNG", "VIMTABEAML", "VIMTALABS",
        "VINDHYATEL", "VINEETLAB", "VINETFASH", "VINYLINDIA", "VIPCLOTHNG",
        "VIPIND", "VIPUL", "VIRANCHI", "VIRATSOLAR", "VIRINCHI",
        "VISAGAR", "VISASTEEL", "VISESHINFO", "VISHNU", "VIVIDHA",
        "VIVIMEDLAB", "VKMGLOBAL", "VKSPL", "VLL", "VLSFINANCE",
        "VMART", "VOLTAMP", "VOLTAS", "VORAGE", "VPIL",
        "VRLLOG", "VSEC", "VSTIND", "VSTTILLERS", "VTLCL",
        "WAAREE", "WABAG", "WAREEENERG", "WATERBASE", "WEALTHFINT",
        "WEALTHFIRST", "WEBSOFT", "WEBTEL", "WEGOTTHI", "WELCORP",
        "WELENT", "WELINV", "WELSPUNIND", "WENDT", "WESTLIFE",
        "WHEELINTAI", "WHIRLPOOL", "WIPL", "WIPRO", "WOCKPHARMA",
        "WONDERLA", "WORTH", "WPIL", "WSI", "WSTCSTPAPR",
        "XCHANGING", "XELPMOC", "XPRO", "YASHCHEMPR", "YASHMGT",
        "YASHPAK", "YATHARTH", "YATRA", "YESBANK", "YUKEN",
        "ZAGGLE", "ZEEL", "ZENITHEXPO", "ZENITHSTL", "ZENSARTECH",
        "ZENSAR", "ZENTEC", "ZFCVINDIA", "ZIMLAB", "ZODIACLOTH",
        "ZOMATO", "ZODJRDMKJ", "ZOTA", "ZUARI", "ZUARIIND",
        "ZYDUSLIFE", "ZYDUSWELL"
    ]

    all_symbols.update(comprehensive_list)

    # Clean up symbols
    all_symbols = {s.strip().upper() for s in all_symbols if s and len(s) > 0}

    return sorted(list(all_symbols))


def download_stock_data(symbol, start_date, end_date):
    """Download data for a single stock."""
    try:
        yf_symbol = f"{symbol}.NS"
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(start=start_date, end=end_date, interval="1d")

        if df.empty:
            return None, symbol

        df = df.reset_index()
        df["symbol"] = symbol
        df["sector"] = SECTOR_MAP.get(symbol, "Other")

        df = df.rename(columns={
            "Date": "trade_date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume"
        })

        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
        df["turnover"] = df["close"] * df["volume"]
        df["prev_close"] = df["close"].shift(1)
        df = df.dropna(subset=["prev_close"])

        return df, None

    except Exception as e:
        return None, symbol


def download_all_stocks(symbols, days=150, max_workers=15):
    """Download data for all stocks using parallel execution."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    logger.info(f"Downloading {len(symbols)} stocks from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    all_data = []
    failed = []

    # Download NIFTY 50 index first
    logger.info("Downloading NIFTY 50 index...")
    try:
        nifty = yf.Ticker("^NSEI")
        nifty_df = nifty.history(start=start_date, end=end_date, interval="1d")
        nifty_df = nifty_df.reset_index()
        nifty_df["symbol"] = "NIFTY50"
        nifty_df = nifty_df.rename(columns={
            "Date": "trade_date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume"
        })
        nifty_df["trade_date"] = pd.to_datetime(nifty_df["trade_date"]).dt.strftime("%Y-%m-%d")
        nifty_df["turnover"] = nifty_df["close"] * nifty_df["volume"]
        nifty_df["prev_close"] = nifty_df["close"].shift(1)
        logger.info(f"NIFTY 50: {len(nifty_df)} days downloaded")
    except Exception as e:
        logger.error(f"Failed to download NIFTY 50: {e}")
        nifty_df = pd.DataFrame()

    # Download stocks in parallel
    logger.info(f"Starting parallel download with {max_workers} workers...")

    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(download_stock_data, symbol, start_date, end_date): symbol
            for symbol in symbols
        }

        for future in as_completed(futures):
            symbol = futures[future]
            completed += 1

            try:
                df, error = future.result()
                if df is not None and not df.empty:
                    all_data.append(df)
                if error:
                    failed.append(error)
            except Exception as e:
                failed.append(symbol)

            if completed % 100 == 0:
                logger.info(f"Progress: {completed}/{len(symbols)} ({len(all_data)} successful, {len(failed)} failed)")

    if all_data:
        combined = pd.concat(all_data, ignore_index=True)
        logger.info(f"Downloaded {len(combined)} records for {len(all_data)} symbols")
        logger.info(f"Failed symbols: {len(failed)}")
        return combined, nifty_df, failed
    else:
        return pd.DataFrame(), nifty_df, failed


def compute_relative_strength(stock_df, nifty_df):
    """Calculate relative strength vs NIFTY."""
    if nifty_df.empty:
        stock_df["relative_strength"] = 1.0
        return stock_df

    nifty_returns = nifty_df.set_index("trade_date")["close"].pct_change()

    result_dfs = []
    for symbol, group in stock_df.groupby("symbol"):
        group = group.sort_values("trade_date").copy()
        stock_returns = group.set_index("trade_date")["close"].pct_change()

        stock_cum = (1 + stock_returns).rolling(20).apply(lambda x: x.prod() - 1)
        nifty_cum = (1 + nifty_returns).rolling(20).apply(lambda x: x.prod() - 1)

        rs = stock_cum / nifty_cum.reindex(stock_cum.index)
        rs = rs.fillna(1.0)

        group = group.reset_index(drop=True)
        group["relative_strength"] = rs.values[-len(group):]

        result_dfs.append(group)

    return pd.concat(result_dfs, ignore_index=True)


def main():
    """Main entry point."""
    logger.info("=" * 70)
    logger.info("COMPLETE NSE DATA DOWNLOAD - ALL STOCKS")
    logger.info("=" * 70)

    # Get complete stock list
    symbols = get_all_nse_symbols()
    logger.info(f"Total symbols to download: {len(symbols)}")

    # Initialize database
    db = Database(config.db_path)

    # Clear existing data
    logger.info("Clearing existing data...")
    with db.get_connection() as conn:
        conn.execute("DELETE FROM screener_results")
        conn.execute("DELETE FROM indicators")
        conn.execute("DELETE FROM eod")
        conn.commit()

    # Download all stocks
    stock_df, nifty_df, failed = download_all_stocks(symbols, days=150, max_workers=15)

    if stock_df.empty:
        logger.error("No data downloaded!")
        return 1

    # Store EOD data
    logger.info("Storing EOD data...")
    cols = ["symbol", "trade_date", "open", "high", "low", "close", "volume", "turnover", "prev_close"]
    db.upsert_eod_data(stock_df[cols])

    # Compute indicators
    logger.info("Computing technical indicators...")
    all_with_indicators = []

    for symbol, group in stock_df.groupby("symbol"):
        group = group.sort_values("trade_date").copy()
        with_ind = add_advanced_indicators(group)
        all_with_indicators.append(with_ind)

    full_df = pd.concat(all_with_indicators, ignore_index=True)

    # Relative strength
    logger.info("Calculating relative strength...")
    full_df = compute_relative_strength(full_df, nifty_df)

    # Store indicators
    logger.info("Storing indicators...")
    indicator_cols = ["symbol", "trade_date", "sma_20", "sma_50", "rsi_14", "atr_14", "vol_ma_20", "hh_20", "ll_20"]
    indicators_df = full_df[indicator_cols].dropna()
    db.upsert_indicators(indicators_df)

    # Run screener
    latest_date = full_df["trade_date"].max()
    latest = full_df[full_df["trade_date"] == latest_date].copy()

    logger.info(f"Running screener on {len(latest)} stocks...")
    results = run_advanced_screener(latest, top_n=50, capital_per_trade=100000, min_score=8)

    if not results.empty:
        db.save_screener_results(results, latest_date)

    # Summary
    print()
    print("=" * 70)
    print("DOWNLOAD COMPLETE")
    print("=" * 70)
    print(f"Symbols attempted: {len(symbols)}")
    print(f"Symbols successful: {len(stock_df['symbol'].unique())}")
    print(f"Symbols failed: {len(failed)}")
    print(f"Total records: {len(stock_df)}")
    print(f"Date range: {stock_df['trade_date'].min()} to {stock_df['trade_date'].max()}")
    print(f"Sectors found: {len(stock_df['sector'].unique())}")
    print(f"Screener candidates: {len(results)}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
