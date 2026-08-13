# Instrument metadata for the 131-symbol scan.
#   name : full instrument name (FirstRateData naming)
#   tick : minimum price increment in PRICE UNITS (same units as the OHLC data)
#
# tick=None means NOT YET VERIFIED. backtest_hull applies zero slippage when
# tick is missing, so an unverified symbol silently reports pre-cost results.
# Verify against the exchange contract spec before trusting any costed number.

INSTRUMENTS = {
    'A6'    : dict(tick=0.00005,                      name='Australian Dollar Futures'),
    'AD'    : dict(tick=0.0001,                         name='Canadian Dollar Futures'),  # TODO verify tick
    'ALI'   : dict(tick=0.25,                        name='Aluminum'),
    'B'     : dict(tick=0.01,                         name='Brent Crude'),  # TODO verify tick
    'B6'    : dict(tick=0.0001,                      name='British Pound Futures'),
    'BFX'   : dict(tick=0.5,                         name='BEL 20'),  # TODO verify tick
    'BR'    : dict(tick=0.00005,                       name='Brazilian Real Futures'),
    'BTC'   : dict(tick=5.0,                         name='Bitcoin Futures'),
    'BZ'    : dict(tick=0.01,                        name='Brent Last Day Financial Futures'),
    'C'     : dict(tick=1,                         name='Cocoa Futures (London)'),  # TODO verify tick
    'CB'    : dict(tick=0.00025,                         name='Cash-settled Butter'),  # TODO verify tick
    'CC'    : dict(tick=1,                         name='Cocoa (New York)'),  # TODO verify tick
    'CL'    : dict(tick=0.01,                        name='Crude Oil WTI Futures'),
    'CNH'   : dict(tick=0.0001,                         name='USD/Offshore RMB'),  # TODO verify tick
    'CSC'   : dict(tick=0.001,                         name='Cash-Settled Cheese'),  # TODO verify tick
    'CT'    : dict(tick=0.01,                         name='Cotton #2 Futures'),  # TODO verify tick
    'DC'    : dict(tick=0.01,                         name='Class III Milk'),  # TODO verify tick
    'DX'    : dict(tick=0.005,                       name='US Dollar Index Future'),
    'E1'    : dict(tick=0.0001,                      name='Swiss Franc Futures'),
    'E6'    : dict(tick=5e-05,                       name='Euro FX Futures'),
    'E7'    : dict(tick=0.0001,                      name='E-mini Euro FX'),
    'EBM'   : dict(tick=0.25,                         name='Milling Wheat Futures'),  # TODO verify tick
    'ER'    : dict(tick=0.005,                         name='3-Month Euribor'),  # TODO verify tick
    'ES'    : dict(tick=0.25,                        name='E-Mini S&P 500 Futures'),
    'ESG'   : dict(tick=0.25,                        name='E-mini S&P 500 ESG Futures'),
    'EW'    : dict(tick=0.1,                         name='e-Mini S&P 400 Midcap Futures'),
    'FBON'  : dict(tick=0.01,                         name='Euro-BONO Futures'),  # TODO verify tick
    'FBTP'  : dict(tick=0.01,                         name='Euro BTP Long-Bond Futures'),  # TODO verify tick
    'FBTS'  : dict(tick=0.005,                         name='Short-Term Euro-BTP'),  # TODO verify tick
    'FCE'   : dict(tick=0.5,                         name='CAC40 Futures'),  # TODO verify tick
    'FDAX'  : dict(tick=1.0,                         name='DAX Futures'),  # TODO verify tick
    'FDIV'  : dict(tick=0.05,                         name='DivDAX'),  # TODO verify tick
    'FDXM'  : dict(tick=1,                         name='Mini DAX'),  # TODO verify tick
    'FDXS'  : dict(tick=1,                         name='Micro DAX'),  # TODO verify tick
    'FESX'  : dict(tick=1,                         name='Euro Stoxx 50 Futures'),  # TODO verify tick
    'FEU3'  : dict(tick=0.00125,                         name='Three-Month EURIBOR (Eurex)'),  # TODO verify tick
    'FGBL'  : dict(tick=0.01,                         name='Euro Bund Futures'),  # TODO verify tick
    'FGBM'  : dict(tick=0.01,                         name='Euro Bobl Futures'),  # TODO verify tick
    'FGBS'  : dict(tick=0.005,                         name='Euro-Schatz'),  # TODO verify tick
    'FGBX'  : dict(tick=0.02,                         name='Euro-Buxl'),  # TODO verify tick
    'FMWO'  : dict(tick=0.10,                         name='MSCI World Index Futures (Eurex)'),  # TODO verify tick
    'FOAT'  : dict(tick=0.01,                         name='Euro-OAT'),  # TODO verify tick
    'FSMX'  : dict(tick=1,                         name='Mini-MDAX'),  # TODO verify tick
    'FTDX'  : dict(tick=0.5,                         name='TecDAX'),  # TODO verify tick
    'FTI'   : dict(tick=0.05,                         name='Amsterdam Index Futures'),  # TODO verify tick
    'FTUK'  : dict(tick=0.5,                         name='FTSE 100 Futures'),  # TODO verify tick
    'FVSA'  : dict(tick=0.05,                         name='VSTOXX Futures'),  # TODO verify tick
    'FXXP'  : dict(tick=0.1,                         name='STOXX Europe 600 Index'),  # TODO verify tick
    'G'     : dict(tick=0.01,                         name='10-Year Long Gilt Futures'),  # TODO verify tick
    'GC'    : dict(tick=0.1,                         name='Gold Futures'),
    'GF'    : dict(tick=0.00025,                       name='Feeder Cattle Futures'),
    'GSCI'  : dict(tick=0.05,                         name='S&P GSCI Futures'),  # TODO verify tick
    'HE'    : dict(tick=0.00025,                       name='Lean Hog Futures'),
    'HG'    : dict(tick=0.0005,                      name='Copper Futures'),
    'HH'    : dict(tick=0.001,                       name='Natural Gas Henry Hub Last-day Financial Futures'),
    'HO'    : dict(tick=0.0001,                      name='NY Harbor ULSD (Heating Oil) Futures'),
    'HRC'   : dict(tick=1,                         name='US Midwest Domestic Hot-Rolled Coil Steel Index'),  # TODO verify tick
    'J1'    : dict(tick=0.0000001,                       name='Japanese Yen Futures'),
    'J7'    : dict(tick=0.000001,                       name='E-mini Japanese Yen'),
    'JB'    : dict(tick=0.01,                         name='UNKNOWN — not in the FirstRateData list; identify before use'),  # TODO verify tick
    'KC'    : dict(tick=0.05,                         name='Coffee Futures'),  # TODO verify tick
    'KE'    : dict(tick=0.0025,                        name='Kansas City Hard Red Winter Wheat Futures'),
    'KRW'   : dict(tick=0.0000001,                         name='KRW/USD (Korean Won / USD)'),  # TODO verify tick
    'L'     : dict(tick=0.0025,                         name='3 Month Sterling Futures'),  # TODO verify tick
    'LBS'   : dict(tick=0.1,                         name='Random Length Lumber Futures'),  # TODO verify tick
    'LE'    : dict(tick=0.00025,                       name='Live Cattle Futures'),
    'M2K'   : dict(tick=0.1,                         name='Micro E-mini Russell 2000 Index Futures'),
    'MAX'   : dict(tick=0.25,                         name='AEX Mini'),  # TODO verify tick
    'MBT'   : dict(tick=5.0,                         name='Micro Bitcoin Futures'),
    'MCL'   : dict(tick=0.01,                        name='Micro WTI Crude Oil Futures'),
    'MES'   : dict(tick=0.25,                        name='Micro E-mini S&P 500 Futures'),
    'MET'   : dict(tick=0.5,                         name='Ether Micro'),
    'MFC'   : dict(tick=0.5,                         name='CAC 40 Mini'),  # TODO verify tick
    'MFS'   : dict(tick=0.1,                         name='Mini MSCI EAFE Futures'),  # TODO verify tick
    'MGC'   : dict(tick=0.1,                         name='Micro Gold Futures'),
    'MME'   : dict(tick=0.1,                         name='MSCI Emerging Markets Index Futures'),  # TODO verify tick
    'MNQ'   : dict(tick=0.25,                        name='Micro E-mini Nasdaq-100 Futures'),
    'MP'    : dict(tick=1e-05,                       name='Mexican Peso Futures'),
    'MURA'  : dict(tick=0.1,                         name='MSCI China'),  # TODO verify tick
    'N6'    : dict(tick=0.0001,                      name='New Zealand Dollar Futures'),
    'NG'    : dict(tick=0.001,                       name='Henry Hub Natural Gas Futures'),
    'NIY'   : dict(tick=5,                         name='Nikkei 225 Yen Futures'),  # TODO verify tick
    'NKD'   : dict(tick=5,                         name='Nikkei 225 Dollar Futures'),  # TODO verify tick
    'NOK'   : dict(tick=0.000025,                         name='Norwegian Krone'),  # TODO verify tick
    'NQ'    : dict(tick=0.25,                        name='E-mini Nasdaq-100 Futures'),
    'OJ'    : dict(tick=0.05,                         name='Orange Juice Futures'),  # TODO verify tick
    'PA'    : dict(tick=0.05,                        name='Palladium Futures'),
    'PJY'   : dict(tick=0.1,                         name='Pound / Yen Futures'),  # TODO verify tick
    'PL'    : dict(tick=0.1,                         name='Platinum Futures'),
    'PRK'   : dict(tick=0.00025,                         name='Pork Cutout'),  # TODO verify tick
    'PSI'   : dict(tick=1,                         name='PSI 20'),  # TODO verify tick
    'QG'    : dict(tick=0.005,                       name='Natural Gas Mini Futures'),
    'RB'    : dict(tick=0.0001,                      name='RBOB Gasoline Futures'),
    'RM'    : dict(tick=1,                         name='Robusta Coffee Futures'),  # TODO verify tick
    'RP'    : dict(tick=0.00005,                         name='Euro-British Pound Futures'),  # TODO verify tick
    'RS'    : dict(tick=0.1,                         name='Canola Futures'),  # TODO verify tick
    'RTY'   : dict(tick=0.1,                         name='e-Mini Russell 2000'),
    'RY'    : dict(tick=0.01,                         name='Euro / Yen Futures'),  # TODO verify tick
    'SB'    : dict(tick=0.01,                         name='Sugar #11 Futures'),  # TODO verify tick
    'SEK'   : dict(tick=0.00001,                         name='Swedish Krona'),  # TODO verify tick
    'SI'    : dict(tick=0.005,                       name='Silver Futures'),
    'SIL'   : dict(tick=0.005,                       name='Micro Silver Futures'),
    'SIR'   : dict(tick=0.01,                         name='INR/USD (Indian Rupee / USD)'),  # TODO verify tick
    'SO3'   : dict(tick=0.0025,                         name='3-Month SONIA'),  # TODO verify tick
    'SR1'   : dict(tick=0.0025,                         name='1 Month SOFR Futures'),  # TODO verify tick
    'SR3'   : dict(tick=0.005,                         name='3 Month SOFR Futures'),  # TODO verify tick
    'T6'    : dict(tick=2.5e-05,                     name='South African Rand Futures'),
    'TN'    : dict(tick=0.015625,                    name='Ultra 10-Year US Treasury Note Futures'),
    'TTF'   : dict(tick=0.005,                         name='Dutch TTF Natural Gas futures'),  # TODO verify tick
    'UB'    : dict(tick=0.03125,                     name='Ultra US Treasury Bond Futures'),
    'US'    : dict(tick=0.03125,                     name='30 Year US Treasury Bond Future'),
    'VX'    : dict(tick=0.05,                        name='VIX Futures'),
    'VXM'   : dict(tick=0.05,                        name='Mini VIX Futures'),
    'XAE'   : dict(tick=0.1,                         name='E-mini Energy Select Sector Futures'),  # TODO verify tick
    'XAF'   : dict(tick=0.05,                         name='E-mini Financial Select Sector Futures'),  # TODO verify tick
    'XAI'   : dict(tick=0.1,                         name='E-mini Industrial Select Sector Futures'),  # TODO verify tick
    'XC'    : dict(tick=0.125,                       name='Corn Mini Futures'),
    'YM'    : dict(tick=1.0,                         name='Dow Futures Mini'),
    'ZC'    : dict(tick=0.25,                        name='Corn Futures'),
    'ZF'    : dict(tick=0.0078125,                   name='5-Year Treasury Note Futures'),
    'ZL'    : dict(tick=0.01,                        name='Soybean Oil Futures'),
    'ZM'    : dict(tick=0.1,                         name='Soybean Meal Futures'),
    'ZN'    : dict(tick=0.015625,                    name='10-Year Treasury Note Futures'),
    'ZO'    : dict(tick=0.25,                        name='Oats Futures'),
    'ZQ'    : dict(tick=0.0025,                      name='30 Day Fed Funds Future'),
    'ZR'    : dict(tick=0.005,                       name='Rough Rice Futures'),
    'ZRPA'  : dict(tick=0.1,                         name='MSCI Europe'),  # TODO verify tick
    'ZS'    : dict(tick=0.25,                        name='Soybean Futures'),
    'ZT'    : dict(tick=0.001953125,                 name='2-Year Treasury Note Futures'),
    'ZTWA'  : dict(tick=0.1,                         name='MSCI Emerging Markets Asia'),  # TODO verify tick
    'ZW'    : dict(tick=0.25,                        name='Wheat Futures'),
}

TICKS = {k: v['tick'] for k, v in INSTRUMENTS.items() if v['tick'] is not None}
UNVERIFIED = sorted(k for k, v in INSTRUMENTS.items() if v['tick'] is None)

if __name__ == '__main__':
    print(f'{len(TICKS)} verified, {len(UNVERIFIED)} unverified')
    print('unverified:', ', '.join(UNVERIFIED))
