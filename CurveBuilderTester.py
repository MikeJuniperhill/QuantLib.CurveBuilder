import json, re, os, sys
from datetime import datetime
import numpy as np
import pandas as pd
import QuantLib as ql

class Configurations:
    inner = {}
    # read JSON configuration file to dictionary
    def __init__(self, filePathName):
        self.inner = json.load(open(filePathName))
    # return value for a given configuration key
    def __getitem__(self, key):
        return self.inner[key.upper()]

# utility class for different QuantLib type conversions 
class Convert:
    
    # convert date string ('yyyy-mm-dd') to QuantLib Date object
    def to_date(s):
        monthDictionary = {
            '01': ql.January, '02': ql.February, '03': ql.March,
            '04': ql.April, '05': ql.May, '06': ql.June,
            '07': ql.July, '08': ql.August, '09': ql.September,
            '10': ql.October, '11': ql.November, '12': ql.December
        }
        s = s.split('-')
        return ql.Date(int(s[2]), monthDictionary[s[1]], int(s[0]))
    
    # convert string to QuantLib businessdayconvention enumerator
    def to_businessDayConvention(s):
        if (s.upper() == 'FOLLOWING'): return ql.Following
        if (s.upper() == 'MODIFIEDFOLLOWING'): return ql.ModifiedFollowing
        if (s.upper() == 'PRECEDING'): return ql.Preceding
        if (s.upper() == 'MODIFIEDPRECEDING'): return ql.ModifiedPreceding
        if (s.upper() == 'UNADJUSTED'): return ql.Unadjusted
        
    # convert string to QuantLib calendar object
    def to_calendar(s):
        if (s.upper() == 'TARGET'): return ql.TARGET()
        if (s.upper() == 'UNITEDSTATES'): return ql.UnitedStates()
        if (s.upper() == 'UNITEDKINGDOM'): return ql.UnitedKingdom()
        # TODO: add new calendar here
        
    # convert string to QuantLib swap type enumerator
    def to_swapType(s):
        if (s.upper() == 'PAYER'): return ql.VanillaSwap.Payer
        if (s.upper() == 'RECEIVER'): return ql.VanillaSwap.Receiver
        
    # convert string to QuantLib frequency enumerator
    def to_frequency(s):
        if (s.upper() == 'DAILY'): return ql.Daily
        if (s.upper() == 'WEEKLY'): return ql.Weekly
        if (s.upper() == 'MONTHLY'): return ql.Monthly
        if (s.upper() == 'QUARTERLY'): return ql.Quarterly
        if (s.upper() == 'SEMIANNUAL'): return ql.Semiannual
        if (s.upper() == 'ANNUAL'): return ql.Annual

    # convert string to QuantLib date generation rule enumerator
    def to_dateGenerationRule(s):
        if (s.upper() == 'BACKWARD'): return ql.DateGeneration.Backward
        if (s.upper() == 'FORWARD'): return ql.DateGeneration.Forward
        # TODO: add new date generation rule here

    # convert string to QuantLib day counter object
    def to_dayCounter(s):
        if (s.upper() == 'ACTUAL360'): return ql.Actual360()
        if (s.upper() == 'ACTUAL365FIXED'): return ql.Actual365Fixed()
        if (s.upper() == 'ACTUALACTUAL'): return ql.ActualActual()
        if (s.upper() == 'ACTUAL365NOLEAP'): return ql.Actual365NoLeap()
        if (s.upper() == 'BUSINESS252'): return ql.Business252()
        if (s.upper() == 'ONEDAYCOUNTER'): return ql.OneDayCounter()
        if (s.upper() == 'SIMPLEDAYCOUNTER'): return ql.SimpleDayCounter()
        if (s.upper() == 'THIRTY360'): return ql.Thirty360()

    # convert string (ex.'USD.3M') to QuantLib ibor index object
    def to_iborIndex(s):
        s = s.split('.')
        if(s[0].upper() == 'USD'): return ql.USDLibor(ql.Period(s[1]))
        if(s[0].upper() == 'EUR'): return ql.Euribor(ql.Period(s[1]))
        
# create piecewise yield term structure
class PiecewiseCurveBuilder(object):
    
    # in constructor, we store all possible instrument conventions and market data
    def __init__(self, settlementDate, conventions, marketData):        
        self.helpers = [] # list containing bootstrap helpers
        self.settlementDate = settlementDate
        self.conventions = conventions
        self.market = marketData
    
    # for a given currency, first assemble bootstrap helpers, 
    # then construct yield term structure handle
    def Build(self, currency, enableExtrapolation = True):

        # clear all existing bootstrap helpers from list
        self.helpers.clear()
        # filter out correct market data set for a given currency
        data = self.market.loc[self.market['Ticker'].str.contains(currency), :]
        
        # loop through market data set
        for i in range(data.shape[0]):            
            # extract ticker and value
            ticker = data.iloc[i]['Ticker']
            value = data.iloc[i]['Value'] 
            
            # add deposit rate helper
            # ticker prototype: 'CCY.DEPOSIT.3M'
            if('DEPOSIT' in ticker):
                # extract correct instrument convention
                convention = self.conventions[currency]['DEPOSIT']
                rate = value
                period = ql.Period(ticker.split('.')[2])
                # extract parameters from instrument convention
                fixingDays = convention['FIXINGDAYS']
                calendar = Convert.to_calendar(convention['CALENDAR'])
                businessDayConvention = Convert.to_businessDayConvention(convention['BUSINESSDAYCONVENTION'])
                endOfMonth = convention['ENDOFMONTH']
                dayCounter = Convert.to_dayCounter(convention['DAYCOUNTER'])
                # create and append deposit helper into helper list
                self.helpers.append(ql.DepositRateHelper(rate, period, fixingDays, 
                    calendar, businessDayConvention, endOfMonth, dayCounter))
        
            # add futures rate helper
            # ticker prototype: 'CCY.FUTURE.10M'
            # note: third ticker field ('10M') is defining starting date
            # for future to be 10 months after defined settlement date
            if('FUTURE' in ticker):
                # extract correct instrument convention
                convention = self.conventions[currency]['FUTURE']
                price = value
                iborStartDate = ql.IMM.nextDate(self.settlementDate + ql.Period(ticker.split('.')[2]))
                # extract parameters from instrument convention
                lengthInMonths = convention['LENGTHINMONTHS']
                calendar = Convert.to_calendar(convention['CALENDAR'])
                businessDayConvention = Convert.to_businessDayConvention(convention['BUSINESSDAYCONVENTION']) 
                endOfMonth = convention['ENDOFMONTH']
                dayCounter = Convert.to_dayCounter(convention['DAYCOUNTER'])
                # create and append futures helper into helper list
                self.helpers.append(ql.FuturesRateHelper(price, iborStartDate, lengthInMonths,
                    calendar, businessDayConvention, endOfMonth, dayCounter))                
            
            # add swap rate helper
            # ticker prototype: 'CCY.SWAP.2Y'
            if('SWAP' in ticker):
                # extract correct instrument convention
                convention = self.conventions[currency]['SWAP']
                rate = value
                periodLength = ql.Period(ticker.split('.')[2])
                # extract parameters from instrument convention
                fixedCalendar = Convert.to_calendar(convention['FIXEDCALENDAR'])
                fixedFrequency = Convert.to_frequency(convention['FIXEDFREQUENCY']) 
                fixedConvention = Convert.to_businessDayConvention(convention['FIXEDCONVENTION'])
                fixedDayCount = Convert.to_dayCounter(convention['FIXEDDAYCOUNTER'])
                floatIndex = Convert.to_iborIndex(convention['FLOATINDEX']) 
                # create and append swap helper into helper list
                self.helpers.append(ql.SwapRateHelper(rate, periodLength, fixedCalendar,
                    fixedFrequency, fixedConvention, fixedDayCount, floatIndex))
        
        # extract day counter for curve from configurations
        dayCounter = Convert.to_dayCounter(self.conventions[currency]['CONFIGURATIONS']['DAYCOUNTER'])
        # construct yield term structure handle
        yieldTermStructure = ql.PiecewiseLinearZero(self.settlementDate, self.helpers, dayCounter)
        if(enableExtrapolation == True): yieldTermStructure.enableExtrapolation()
        return ql.RelinkableYieldTermStructureHandle(yieldTermStructure)

# program execution starts here
# create instrument conventions and market data
rootDirectory = sys.argv[1] #command line argument, such as '/home/mikejuniperhill/QuantLib/'
evaluationDate = Convert.to_date(datetime.today().strftime('%Y-%m-%d'))
ql.Settings.instance().evaluationDate = evaluationDate
# it is expected that these files are stored in root directory
conventions = Configurations(rootDirectory + 'conventions.json')
marketData = pd.read_csv(rootDirectory + 'marketdata.csv')

# initialize builder, store all conventions and market data
builder = PiecewiseCurveBuilder(evaluationDate, conventions, marketData)
currencies = sys.argv[2] #command line argument, such as 'USD,EUR'
currencies = currencies.split(',')

# construct curves based on instrument conventions, given market data and currencies
for currency in currencies:    
    curve = builder.Build(currency)
    # print discount factors semiannually up to 30 years
    times = np.linspace(0.0, 30.0, 61)
    df = [round(curve.discount(t), 4) for t in times]
    print('discount factors for', currency)
    print(df)

