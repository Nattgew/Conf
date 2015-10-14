#!/usr/bin/python
from xml.dom import minidom
import urllib.request
import math
import os, re, fileinput, csv, sqlite3
import locale, time
import sys, getopt
import dicts
from datetime import timedelta, date, datetime
from mpl_toolkits.basemap import Basemap
from matplotlib.dates import DateFormatter, date2num
import matplotlib.pyplot as plt

def getkey():
	file='/mnt/data/XPLANE10/XSDK/mykey.txt'
	with open(file, 'r') as f:
		mykey = f.readline()
	mykey=mykey.strip()
	return mykey

def getname():
	file='/mnt/data/XPLANE10/XSDK/mykey.txt'
	with open(file, 'r') as f:
		nothing = f.readline()
		myname = f.readline()
	myname=myname.strip()
	return myname

def fserequest(ra,rqst,tagname):
	if ra==1:
		rakey="&readaccesskey="+getkey()
	else:
		rakey=""
	data = urllib.request.urlopen('http://server.fseconomy.net/data?userkey='+getkey()+rakey+'&format=xml&'+rqst)
	print("Parsing data...")
	xmldoc = minidom.parse(data)
	error = xmldoc.getElementsByTagName('Error')
	if error!=[]:
		print("Received error: "+error[0].firstChild.nodeValue)
		tags=[]
	else:
		tags = xmldoc.getElementsByTagName(tagname)
	return tags

def acforsale(conn): #Log aircraft currently for sale
	print("Sending request for sales listing...")
	airplanes = fserequest(0,'query=aircraft&search=forsale','Aircraft')
	print("Recording data...")
	c=getdbcon(conn)
	count=getmaxiter(conn)
	count+=1
	now=time.strftime("%Y-%m-%d %H:%M", time.gmtime())
	row=(count, now)
	c.execute('INSERT INTO queries VALUES (?,?);',row) #Record date/time of this query
	for airplane in airplanes: #Record aircraft for sale
		actype = airplane.getElementsByTagName("MakeModel")[0].firstChild.nodeValue
		serial = int(airplane.getElementsByTagName("SerialNumber")[0].firstChild.nodeValue)
		aframetime = airplane.getElementsByTagName("AirframeTime")[0].firstChild.nodeValue
		hours = int(aframetime.split(":")[0])
		price = float(airplane.getElementsByTagName("SalePrice")[0].firstChild.nodeValue)
		loc = airplane.getElementsByTagName("Location")[0].firstChild.nodeValue
		locname = airplane.getElementsByTagName("LocationName")[0].firstChild.nodeValue
		row=(serial, actype, loc, locname, hours, price, count)
		c.execute('INSERT INTO allac VALUES (?,?,?,?,?,?,?);',row)
	conn.commit()
	
def logpaymonth(conn,year,month): #Log a month of payments
	print("Sending requrest for payment listing...")
	payments = fserequest(1,'query=payments&search=monthyear&month='+month+'&year='+year,'Payment')
	c=getpaydbcon(conn)
	print("Recording data...")
	for payment in payments:
		pdate = payment.getElementsByTagName("Date")[0].firstChild.nodeValue
		to = payment.getElementsByTagName("To")[0].firstChild.nodeValue
		fr = payment.getElementsByTagName("From")[0].firstChild.nodeValue
		amt = float(payment.getElementsByTagName("Amount")[0].firstChild.nodeValue)
		rsn = payment.getElementsByTagName("Reason")[0].firstChild.nodeValue
		loc = payment.getElementsByTagName("Location")[0].firstChild.nodeValue
		pid = int(payment.getElementsByTagName("Id")[0].firstChild.nodeValue)
		#print("pdate="+pdate+"  to="+to+"  from="+fr+"  amount="+str(amt)+"  reason="+rsn+"  loc="+loc)
		if rsn=="Monthly Interest" or rsn=="Fuel Delivered" or rsn=="Sale of wholesale JetA" or rsn=="Sale of wholesale 100LL" or rsn=="Sale of supplies" or rsn=="Sale of building materials" or rsn=="Transfer of supplies" or rsn=="Transfer of building materials" or rsn=="Group payment" or rsn=="FBO sale" or rsn=="Transfer of JetA" or rsn=="Transfer of 100LL": #Broken XML
			ac = "null"
		else:
			ac = payment.getElementsByTagName("Aircraft")[0].firstChild.nodeValue
		pdate=pdate.replace('/','-')
		row=(pdate, to, fr, amt, rsn, loc, ac, pid)
		c.execute('INSERT INTO payments VALUES (?,?,?,?,?,?,?,?);',row)
	conn.commit()
	
def getdbcon(conn): #Get cursor for aircraft sale database
	print("Initializing database cursor...")
	c = conn.cursor()
	c.execute("select count(*) from sqlite_master where type = 'table';")
	exist=c.fetchone()
	#print("Found " + str(exist[0]) + " tables...")
	if  exist[0]==0: #Table does not exist, create table
		print("Creating tables...")
		c.execute('''CREATE TABLE allac
			 (serial real, type text, loc text, locname text, hours real, price real, obsiter real)''')
		c.execute('''CREATE TABLE queries
			 (obsiter real, qtime text)''')
		conn.commit()
	return c
	
def getpaydbcon(conn): #Get cursor for payment database
	print("Initializing payment database cursor...")
	c = conn.cursor()
	c.execute("select count(*) from sqlite_master where type = 'table';")
	exist=c.fetchone()
	#print("Found " + str(exist[0]) + " tables...")
	if  exist[0]==0: #Table does not exist, create table
		print("Creating tables...")
		c.execute('''CREATE TABLE payments
			 (date text, payto text, payfrom text, amount real, reason text, location text, aircraft text, pid real)''')
		c.execute('''CREATE INDEX idx1 ON payments(date)''')
		conn.commit()
	return c
	
def getmaxiter(conn): #Return the number of latest query, which is the number of queries
	c = conn.cursor()
	c.execute('SELECT iter FROM queries ORDER BY iter DESC;')
	count=c.fetchone()
	#print("Found "+str(count)+" previous queries")
	if count is not None:
		current=int(count[0])
	else:
		current=0
	return current

def dudewheresmyairplane(): #Print list of owned planes
	#planes={}
	print("Sending request for aircraft list...")
	airplanes = fserequest(1,'query=aircraft&search=key','Aircraft')
	for plane in airplanes:
		loc = plane.getElementsByTagName("Location")[0].firstChild.nodeValue
		reg = plane.getElementsByTagName("Registration")[0].firstChild.nodeValue
		eng = plane.getElementsByTagName("EngineTime")[0].firstChild.nodeValue
		chk = plane.getElementsByTagName("TimeLast100hr")[0].firstChild.nodeValue
		#planes[reg]=(loc,eng,chk)
		print(reg+" at "+loc+"  tot: "+eng+"  last: "+chk)
	
def jobsfrom(apts,price,pax): #High paying jobs from airports
	jobs=[]
	print("Sending request for jobs from "+apts+"...")
	assignments = fserequest(0,'query=icao&search=jobsfrom&icaos='+apts,'Assignment')
	for assignment in assignments:
		jobs=jobstest(assignment,jobs,price,pax)
		global totalfrom
		totalfrom+=1
	return jobs

def jobsto(apts,price,pax): #High paying jobs to airports
	jobs=[]
	print("Sending request for jobs to "+apts+"...")
	assignments = fserequest(0,'query=icao&search=jobsto&icaos='+apts,'Assignment')
	for assignment in assignments:
		jobs=jobstest(assignment,jobs,price,pax)
		global totalto
		totalto+=1
	return jobs

def jobstest(assignment,jobs,price,pax): #Only add job to array if meeting minumum pax and pay values
	pay = float(assignment.getElementsByTagName("Pay")[0].firstChild.nodeValue)
	if pay>price:
		amt = assignment.getElementsByTagName("Amount")[0].firstChild.nodeValue
		typ = assignment.getElementsByTagName("UnitType")[0].firstChild.nodeValue
		if not(int(amt)>pax and typ=="passengers"):
			#dep = assignment.getElementsByTagName("FromIcao")[0].firstChild.nodeValue
			arr = assignment.getElementsByTagName("ToIcao")[0].firstChild.nodeValue
			loc = assignment.getElementsByTagName("Location")[0].firstChild.nodeValue
			exp = assignment.getElementsByTagName("Expires")[0].firstChild.nodeValue
			jobs.append((loc,arr,amt,typ,pay,exp))
			#if dep==loc:
			#	print (amt+" "+typ+" "+dep+"-"+arr+" $"+str(int(pay))+" "+exp)
			#else:
			#	print (amt+" "+typ+" @"+loc+"-"+arr+" $"+str(int(pay))+" "+exp)
	return jobs

def paxto(apts,minpax,maxpax): #Pax jobs to airports (incl green jobs)
	print("Sending request incl pax jobs to "+apts+"...")
	assignments = fserequest(0,'query=icao&search=jobsto&icaos='+apts,'Assignment')
	jobs=paxtest(assignments,minpax,maxpax,"to")
	return jobs

def paxfrom(apts,minpax,maxpax): #Pax jobs from airports (incl green jobs)
	print("Sending request incl pax jobs from "+apts+"...")
	assignments = fserequest(0,'query=icao&search=jobsfrom&icaos='+apts,'Assignment')
	jobs=paxtest(assignments,minpax,maxpax,"from")
	return jobs

def paxtest(assignments,minpax,maxpax,tofrom): #Return assignments meeting min and max pax requirements
	candidates=[]
	apts={}
	jobs=[]
	for assignment in assignments:
		loc = assignment.getElementsByTagName("Location")[0].firstChild.nodeValue
		arr = assignment.getElementsByTagName("ToIcao")[0].firstChild.nodeValue
		amt = assignment.getElementsByTagName("Amount")[0].firstChild.nodeValue
		typ = assignment.getElementsByTagName("UnitType")[0].firstChild.nodeValue
		if tofrom=="to":
			global totalto
			totalto+=1
			key=loc
		else:
			global totalfrom
			totalfrom+=1
			key=arr
		if not(int(amt)>maxpax and typ=="passengers") and typ=="passengers":
			amt=int(amt)
			pay = float(assignment.getElementsByTagName("Pay")[0].firstChild.nodeValue)
			#dep = assignment.getElementsByTagName("FromIcao")[0].firstChild.nodeValue
			exp = assignment.getElementsByTagName("Expires")[0].firstChild.nodeValue
			candidates.append((loc,arr,amt,typ,pay,exp))
			try:
				tot=apts[key]
				tot+=amt
			except (KeyError,IndexError) as e:
				tot=amt
			apts[key]=tot
	for option in candidates:
		tot=apts[option[0]]
		if tot>minpax:
			jobs.append(option)
	return jobs

def printjobs(jobs,rev): #Print the list of jobs
	if rev==1:
		list=jobs
	else:
		list=reversed(jobs)
	for job in jobs:
		print(job[2]+" "+job[3]+" "+job[0]+"-"+job[1]+" $"+str(int(job[4]))+" "+str(distbwt(job[0],job[1]))+" "+job[5])
	
def cosinedist(lat1,lon1,lat2,lon2): #Use cosine to find distance between coordinates
	phi1 = math.radians(lat1)
	phi2 = math.radians(lat2)
	dellamb = math.radians(lon2-lon1)
	R = 3440.06479 # Nmi
	# gives d in Nmi
	d = math.acos( math.sin(phi1)*math.sin(phi2) + math.cos(phi1)*math.cos(phi2) * math.cos(dellamb) ) * R
	return int(round(d))

def inithdg(lat1,lon1,lat2,lon2): #Find heading between coordinates
	phi1 = math.radians(lat1)
	phi2 = math.radians(lat2)
	lamb1 = math.radians(lon1)
	lamb2 = math.radians(lon2)
	y = math.sin(lamb2-lamb1) * math.cos(phi2)
	x = math.cos(phi1)*math.sin(phi2) - math.sin(phi1)*math.cos(phi2)*math.cos(lamb2-lamb1)
	brng = math.degrees(math.atan2(y, x))
	if brng<0:
		brng+=360
	return brng

def dirbwt(icaofrom,icaoto): #Find bearing from one airport to another
	lat1,lon1=loc_dict[icaofrom]
	lat2,lon2=loc_dict[icaoto]
	hdg=inithdg(lat1,lon1,lat2,lon2)
	return hdg

def distbwt(icaofrom,icaoto): #Find distance from one airport to another
	lat1,lon1=loc_dict[icaofrom]
	lat2,lon2=loc_dict[icaoto]
	dist=cosinedist(lat1,lon1,lat2,lon2)
	return dist

def build_latlon_csv(): #return dictionary of airport coordinates, using FSE csv file
	loc_dict = {}
	file='/mnt/data/XPLANE10/XSDK/icaodata.csv'
	with open(file, 'r') as f:
		has_header = csv.Sniffer().has_header(f.read(1024))
		f.seek(0)  # rewind
		reader = csv.reader(f)
		if has_header:
			next(reader)  # skip header row
		for row in reader:
			loc_dict[row[0]]=(float(row[1]),float(row[2])) #Code = lat, lon
	return loc_dict

def build_ctry_csv(): #return dictionary of airport countries, using FSE csv file
	loc_dict = {}
	file='/mnt/data/XPLANE10/XSDK/icaodata.csv'
	with open(file, 'r') as f:
		has_header = csv.Sniffer().has_header(f.read(1024))
		f.seek(0)  # rewind
		reader = csv.reader(f)
		if has_header:
			next(reader)  # skip header row
		for row in reader:
			loc_dict[row[0]]=row[8] #Code = Country
	return loc_dict

def chgdir(hdg,delt): #Add delta to heading and fix if passing 0 or 360
	hdg+=delt
	if hdg>360:
		hdg-=360
	elif hdg<=0:
		hdg+=360
	return hdg

def nearby(icao,rad): #Find other airports within radius of given airport
	#print("Looking for airports near "+icao)
	near=""
	clat,clon=loc_dict[icao]
	for apt,coords in loc_dict.items():
		if apt!=icao:
			#print("Dist from "+str(clat)+" "+str(clon)+" to "+str(coords[0])+" "+str(coords[1]))
			dist=cosinedist(clat,clon,coords[0],coords[1])
			if dist<rad:
				if near=="":
					near=apt
				else:					
					near=near+"-"+apt
	#print(near)
	return near

def bigjobs(apts,dir): #Find high paying jobs to/from airports
	total=0
	for airport in apts:
		if dir==0:
			area=nearby(airport,50)
			jobs=jobsfrom(area,30000,8) 
		else:
			jobs=jobsto(airport,30000,8)
		printjobs(jobs,0)
		total+=len(jobs)
	word="from near" if dir==0 else "to"
	print("Found these "+str(total)+" big jobs "+word+" those airports:")
		
def mapper(what, points, mincoords, maxcoords, title): # Put the points on a map, color by division
	print("Mapping points...")
	if maxcoords[1]-mincoords[1]>180 or maxcoords[0]-mincoords[0]>60: # World with center aligned
		m = Basemap(projection='hammer', resolution='c', lon_0=(maxcoords[1]+mincoords[1])/2)
	else: # Center map on area
		width=maxcoords[1]-mincoords[1]
		height=maxcoords[0]-mincoords[0]
		m = Basemap(projection='cyl', resolution='c', llcrnrlon=mincoords[1]-0.1*width, llcrnrlat=mincoords[0]-0.1*height, urcrnrlon=maxcoords[1]+0.1*width, urcrnrlat=maxcoords[0]+0.1*height)
	if what=="ac":
		if len(points) < 30: #Use awesome airplane symbol
			verts = list(zip([0.,1.,1.,10.,10.,9.,6.,1.,1.,4.,1.,0.,-1.,-4.,-1.,-1.,-5.,-9.,-10.,-10.,-1.,-1.,0.],[9.,8.,3.,-1.,-2.,-2.,0.,0.,-5.,-8.,-8.,-9.,-8.,-8.,-5.,0.,0.,-2.,-2.,-1.,3.,8.,9.])) #Supposed to be an airplane
			mk=(verts,0)
			ptsize=50
		else: #Use boring but more compact dots
			mk='o'
			ptsize=2
		m.shadedrelief()
		x, y = m([i[1] for i in points], [i[0] for i in points])
		c='b'
		m.scatter(x,y,s=ptsize,marker=mk,c=c)
	elif what=="fuel":
		max=0
		for loc in points:
			thous=int(round(loc[2])) #Size of point will be based on fuel amount
			if thous>max:
				max=thous
			loc[2]=thous
		pts=[] #rows=thous, columns=colors, contents=list of points
		for i in range(max+1):
			pts.append([[],[],[]]) #Add a new empty row
			for loc in points:
				if loc[2]==i+1:
					pts[i][loc[3]].append((loc[0],loc[1]))
		for i in range(max+1):
			sz=(i+1)*2
			if pts[i]!=[[],[],[]]:
				for j in range(3):
					if pts[i][j]!=[]:
						x, y = m([k[1] for k in pts[i][j]], [k[0] for k in pts[i][j]])
						if j==0:
							c='o'
						elif j==1:
							c='b'
						else:
							c='k'
						m.scatter(x,y,s=sz,marker='o',c=c)
	plt.title(title,fontsize=12)
	plt.show()
	
def gettotals(conn,actype,fr,to): #Return list of total aircraft for sale at each query time
	c=getdbcon(conn)
	d=getdbcon(conn)
	totals=[]
	print("Finding total aircraft for sale from "+fr+" to "+to+"...")
	for query in c.execute('SELECT * FROM queries WHERE qtime BETWEEN ? AND ?', (fr,to)):
		print("Reading query "+str(query[0])+" from "+query[1])
		if actype=="None":
			d.execute('SELECT COUNT(*) FROM allac WHERE obsiter = ?', (query[0],))
		else:
			d.execute('SELECT COUNT(*) FROM allac WHERE obsiter = ? AND type = ?', (query[0],actype))	
		total=int(d.fetchone()[0])
		totals.append((getdtime(query[1]),total))
	return totals

def getaverages(conn,actype,fr,to): #Return list of average prices for aircraft in each query time
	c=getdbcon(conn)
	d=getdbcon(conn)
	averages=[]
	fr=fr+" 00:01" #Add times to match the values in table
	to=to+" 23:59"
	print("Finding averages for: "+actype+" from "+fr+" to "+to+"...")
	for query in c.execute('SELECT * FROM queries WHERE qtime BETWEEN ? AND ?', (fr,to)):
		#print("Matched query "+str(query[0])+":"+query[1])
		numforsale=0
		totalprice=0
		for sale in d.execute('SELECT price FROM allac WHERE obsiter = ? AND type = ?', (query[0],actype)):
			#print("Matched sale for "+str(sale[0]))
			totalprice+=int(sale[0])
			numforsale+=1
		if numforsale>0:
			avg=totalprice/numforsale
			averages.append((getdtime(query[1]),avg))
			#print("Average is "+str(avg))
	return averages

def getdtime(strin): #Return datetime for the Y-M-D H:M input
	adate,atime=strin.split()
	year=int(adate.split('-', 2)[0])
	month=int(adate.split('-', 2)[1])
	day=int(adate.split('-', 2)[2])
	hour=int(atime.split(':')[0])
	mnt=int(atime.split(':')[1])
	return datetime(year,month,day,hour,mnt)

def getlows(conn,actype,fr,to): #Return list of lowest price for aircraft in each query
	c=getdbcon(conn)
	d=getdbcon(conn)
	lows=[]
	print("Finding low low prices for: "+actype+"...")
	for query in c.execute('SELECT * FROM queries WHERE qtime BETWEEN ? AND ?', (fr,to)):
		d.execute('SELECT price FROM allac WHERE obsiter = ? AND type = ? ORDER BY price', (query[0],actype))
		price=d.fetchone()
		if price is not None:
			lows.append((getdtime(query[1]),price))
	return lows

def mapcommo(type):
	if type=="fuel":
		t1="JetA Fuel"
		t2="100LL Fuel"
	elif type=="mtrl":
		t1="Supplies"
		t2="Building materials"
	else:
		print("Commodity type "+type+" not recognized!")
	if t1 is not None:
		print("Sending request for commodities...")
		commo = fserequest(0,'query=commodities&search=key','Commodity')
		print("Sorting results...")
		stuff = []
		for item in commo: #Parse commodity info
			typ = airplane.getElementsByTagName("Type")[0].firstChild.nodeValue
			if typ==t1 or typ==t2:
				loc = airplane.getElementsByTagName("Location")[0].firstChild.nodeValue
				amt = airplane.getElementsByTagName("Amount")[0].firstChild.nodeValue
				stuff.append((loc,typ,amt))
		if stuff!=[]: #Add up quantity per location
			qty=[] #List to hold quantities
			for item in stuff:
				match=-1
				i=-1
				for prev in qty:
					i+=1
					if item[0]==qty[0]: #Test if the location has already been added
						match=1
						break
				if match==-1: #If not added, then add new location/quantity
					if item[1]==t1:
						idx=0
					else: #t2
						idx=1
					qty.append([item[0],item[2].split(),idx])
				else: #If added, then sum with other quantity
					qty[i][1]+=item[2].split()
					qty[i][2]=2 #Indicates a mix of t1 and t2
			coords=getcoords(qty[:][0])
			if len(coords)==len(qty): #If not, there was some key error I guess
				locations=[]
				for i in range(len(coords)):
					locations.append([locations[i][0],locations[i][1],qty[i][1],qty[i][2]])
				mapper(type, locations, (latmin,lonmin), (latmax,lonmax), title)
		else:
			print("No "+type+" found!")

def getlistings(conn,actype,lo,hi): #Return list of time for aircraft to sell
	c=getdbcon(conn)
	d=getdbcon(conn)
	cdict=build_ctry_csv()
	rdict=dicts.getregiondict()
	listings=[]
	print("Finding sell times for: "+actype+", "+str(lo)+" to "+str(hi)+"...")
	for query in c.execute('SELECT obsiter FROM queries'):
	#serial real, type text, loc text, locname text, hours real, price real, obsiter real
		for sale in d.execute('SELECT * FROM allac WHERE obsiter = ? AND type = ? AND price BETWEEN ? AND ?', (query[0],actype,lo,hi)):
			country=cdict[sale[2]]
			region=rdict(country)
			match=0
			for i in range(len(listings)):
				if sale[0]==listings[i][0]:
					if region==listings[i][1] and sale[5]==listings[i][2]:
						listings[i][4]=query[0] #Update "to" date in current list
						match=1
					else:
						listings.remove(listings[i]) #Price/region changed, remove old listing and will append a new one
					break
			if match==0:
				listings.append([sale[0],region,int(sale[5]),query[0],query[0]]) #SN, region, price, first iter, last iter
				
	return listings

def mapaclocations(conn, actype): #Map locations of aircraft type for sale
	c=getdbcon(conn)
	iters=getmaxiter(conn)
	q1="SELECT loc FROM allac WHERE obsiter = "+str(iters) #To allow adding to query
	if actype=="":
		title="Locations of all aircraft for sale"
	else:
		q1+=" AND type = '"+actype+"'"
		title="Locations of "+actype+" for sale"
	locations=getcoords(c.execute(q1))
	mapper(what, locations, (latmin,lonmin), (latmax,lonmax), title)
	
def getcoords(data): #Get coordinates for a list of airports
	print("Building airport location dictionary from csv...")
	loc_dict=build_latlon_csv()
	print("Creating locations list...")
	locations=[]
	lat_tot=0
	lon_tot=0
	latmax,lonmax,latmin,lonmin=100,200,100,200 #garbage to signal init
#	print("Running query: "+q1)
	for row in data:
		try:
			lat,lon=loc_dict[row[0]]
		except KeyError: #Probably "Airborne"
			continue
		locations.append([lat,lon])
		lat_tot+=lat
		lon_tot+=lon
		if lat<latmin or abs(latmin)>90:
			latmin=lat
		if lat>latmax or abs(latmax)>90:
			latmax=lat
		if lon<lonmin or abs(lonmin)>180:
			lonmin=lon
		if lon>lonmax or abs(lonmax)>180:
			lonmax=lon
	pts=len(locations)
	if pts>0:
		#center=(lat_tot/pts,lon_tot/pts)
		pass
	else:
		print("No locations found!")
	return locations
	
def plotdates(dlist,title,ylbl): #Plot a list of data vs. dates
	print("Plotting figure for: "+title)
	fig, ax = plt.subplots()
	formatter=DateFormatter('%Y-%m-%d %H:%M')
	ax.xaxis.set_major_formatter(formatter)
	#print("Attempting to plot the following "+str(len(data))+" dates:")
	#for pdate in [i[0] for i in data]:
	#	print(pdate)
	for data in dlist:
		ax.plot([date2num(i[0]) for i in data], [i[1] for i in data], 'o-')
	formatter=DateFormatter('%Y-%m-%d')
	ax.xaxis.set_major_formatter(formatter)
	fig.autofmt_xdate()
	plt.title(title,fontsize=12)
	plt.xlabel("Date")
	plt.ylabel(ylbl)
	plt.show()
#	plt.xlim([date2num(date(fyear,fmonth,fday)),date2num(date(tyear,tmonth,tday))])
	
def plotpayments(conn,fromdate,todate): #Plot payment totals per category
	c=getpaydbcon(conn)
	user=getname()
	delta=timedelta(days=1)
	fyear=int(fromdate.split('-', 2)[0])
	fmonth=int(fromdate.split('-', 2)[1])
	fday=int(fromdate.split('-', 2)[2])
	tyear=int(todate.split('-', 2)[0])
	tmonth=int(todate.split('-', 2)[1])
	tday=int(todate.split('-', 2)[2])
	fdate=date(fyear,fmonth,fday)
	tdate=date(tyear,tmonth,tday)
	rentexp, rentinc, assnmtexp, assnmtinc, pltfee, addcrewfee, gndcrewfee, bkgfee, ref100, refjet, mxexp, eqinstl, acsold, acbought, fboref100, fborefjet, fbogndcrew, fborepinc, fborepexp, fboeqpexp, fboeqpinc, ptrentinc, ptrentexp, fbosell, fbobuy, wsbuy100, wssell100, wsbuyjet, wsselljet, wsbuybld, wssellbld, wsbuysupp, wssellsupp, grpay=([[fdate,0]] for i in range(34))
	allthat=[rentexp, rentinc, assnmtexp, assnmtinc, pltfee, addcrewfee, gndcrewfee, bkgfee, ref100, refjet, mxexp, eqinstl, acsold, acbought, fboref100, fborefjet, fbogndcrew, fborepinc, fborepexp, fboeqpexp, fboeqpinc, ptrentinc, ptrentexp, fbosell, fbobuy, wsbuy100, wssell100, wsbuyjet, wsselljet, wsbuybld, wssellbld, wsbuysupp, wssellsupp, grpay]
	i=0
	print("Tallying daily payments from "+str(fdate.year)+"-"+str(fdate.month)+" to "+str(tdate.year)+"-"+str(tdate.month)+"...")
	#(date text, to text, from text, amount real, reason text, location real, aircraft real)
	while fdate <= tdate:
		fdateq=fdate.isoformat()+" 00:00:01"
		tdateq=fdate.isoformat()+" 23:59:59"
		if i>0:
			dstring=fdate
			for var in allthat:
				#dstring=str(fdate.year)+"-"+str(fdate.month)+"-"+str(fdate.day)
				var.append([dstring,var[i-1][1]])
		#print("SELECT * FROM payments WHERE date BETWEEN "+fdateq+" AND "+tdateq)
		for payment in c.execute('SELECT * FROM payments WHERE date BETWEEN ? AND ?',(fdateq,tdateq)):
			#print("Found payment: "+payment[4])
			if payment[4]=="Rental of aircraft":
				if payment[2]!=user:
					rentinc[i][1]+=payment[3]
				else:
					rentexp[i][1]+=payment[3]
			elif payment[4]=="Pay for assignment":
				if payment[2]!=user:
					assnmtinc[i][1]+=payment[3]
				else:
					assnmtexp[i][1]+=payment[3]
			elif payment[4]=="Crew fee":
				addcrewfee[i][1]+=payment[3]
			elif payment[4]=="FBO ground crew fee":
				if payment[2]!=user:
					fbogndcrew[i][1]+=payment[3]
				else:
					gndcrewfee[i][1]+=payment[3]
			elif payment[4]=="Booking Fee":
				bkgfee[i][1]+=payment[3]
			elif payment[4]=="Refuelling with JetA":
				if payment[2]!=user:
					fborefjet[i][1]+=payment[3]
				else:
					refjet[i][1]+=payment[3]
			elif payment[4]=="Refuelling with 100LL":
				if payment[2]!=user:
					fboref100[i][1]+=payment[3]
				else:
					ref100[i][1]+=payment[3]
			elif payment[4]=="Aircraft maintenance":
				if payment[2]!=user:
					fborepinc[i][1]+=payment[3]
				else:
					mxexp[i][1]+=payment[3]
			elif payment[4]=="Aircraft sale":
				if payment[2]!=user:
					acsold[i][1]+=payment[3]
				else:
					acbought[i][1]+=payment[3]
			elif payment[4]=="Sale of wholesale JetA":
				if payment[2]!=user:
					wsselljet[i][1]+=payment[3]
				else:
					wsbuyjet[i][1]+=payment[3]
			elif payment[4]=="Sale of wholesale 100LL":
				if payment[2]!=user:
					wssell100[i][1]+=payment[3]
				else:
					wsbuy100[i][1]+=payment[3]
			elif payment[4]=="Sale of supplies":
				if payment[2]!=user:
					wssellsupp[i][1]+=payment[3]
				else:
					wsbuysupp[i][1]+=payment[3]
			elif payment[4]=="Sale of building materials":
				if payment[2]!=user:
					wssellbld[i][1]+=payment[3]
				else:
					wsbuybld[i][1]+=payment[3]
			elif payment[4]=="Group payment":
				if payment[2]!=user:
					grpay[i][1]+=payment[3]
				else:
					grpay[i][1]-=payment[3]
			elif payment[4]=="Pilot fee":
				if payment[2]!=user:
					pltfee[i][1]+=payment[3]
				else:
					pltfee[i][1]-=payment[3]
			elif payment[4]=="Installation of equipment in aircraft":
				if payment[2]!=user:
					fboeqpinc[i][1]+=payment[3]
				else:
					eqinstl[i][1]+=payment[3]
			else:
				print("No category found for "+payment[4])
		fdate += delta
		i += 1
	
	plotdates([refjet, addcrewfee, gndcrewfee],"Money","Money")
	
	# title="Money Stuff"
	# ylbl="Money"
	# print("Plotting figure for: "+title)
	# fig, ax = plt.subplots()
	# #for data in allthat:
		# #print("Attempting to plot the following "+str(len(data))+" dates:")
		# #for pdate in [i[0] for i in data]:
			# #print(pdate)
	# plots=["","",""]
	# j=0
	# for data in [refjet, addcrewfee, gndcrewfee]:
		# plots[j],=ax.plot([date2num(i[0]) for i in data], [i[1] for i in data], '-')
		# j+=1
	# plt.legend(plots,['JetA', 'Addnl Crew', 'Gnd Crew'],loc=2)
	# formatter=DateFormatter('%Y-%m-%d')
	# ax.xaxis.set_major_formatter(formatter)
	# fig.autofmt_xdate()
	# #ax.fmt_xdata=formatter
	# plt.title(title,fontsize=12)
	# plt.xlabel("Date")
	# plt.ylabel(ylbl)
	# plt.xlim([date2num(date(fyear,fmonth,fday)),date2num(date(tyear,tmonth,tday))])
	# plt.show()
	
def sumpayments(conn,fdate,tdate): #Plot portion of income/expense per category
	c=getpaydbcon(conn)
	#Income
	rentinc=[0,"Rental income"]
	assnmtinc=[0,"Assignment income"]
	acsold=[0,"Aircraft sold"]
	fboref100=[0,"100LL pumped"]
	fborefjet=[0,"JetA pumped"]
	fbogndcrew=[0,"Ground crew income"]
	fborepinc=[0,"Repair income"]
	fboeqpinc=[0,"Eqp instl income"]
	ptrentinc=[0,"PT rent income"]
	fbosell=[0,"FBO sold"]
	wssell100=[0,"100LL sold"]
	wsselljet=[0,"JetA sold"]
	wssellbld=[0,"Building materials sold"]
	wssellsupp=[0,"Supplies sold"]
	grpay=[0,"Group payment"]
	
	#Expenses
	rentexp=[0,"Rental expense"]
	assnmtexp=[0,"Assignment expense"]
	pltfee=[0,"Pilot fees"]
	addcrewfee=[0,"Additional crew fee"]
	gndcrewfee=[0,"Ground crew fee"]
	bkgfee=[0,"Booking fee"]
	ref100=[0,"100LL pumped"]
	refjet=[0,"JetA pumped"]
	mxexp=[0,"Maintenance"]
	eqinstl=[0,"Equipment installed"]
	acbought=[0,"Aircraft bought"]
	fborepexp=[0,"FBO repair cost"]
	fboeqpexp=[0,"FBO eqp instl"]
	fbobuy=[0,"FBO bought"]
	wsbuy100=[0,"100LL bought"]
	wsbuyjet=[0,"JetA bought"]
	wsbuybld=[0,"Building materials"]
	wsbuysupp=[0,"Supplies"]

	user=getname()
	fromdate=fdate+" 00:01"
	todate=tdate+" 23:59"
	print("Tallying payments from"+str(fdate[0])+"-"+str(fdate[1])+" to "+str(tdate[0])+"-"+str(tdate[1])+"...")
	#(date text, to text, from text, amount real, reason text, location real, aircraft real)
	for payment in c.execute('SELECT * FROM payments WHERE date BETWEEN ? AND ?',(fromdate,todate)):
		if payment[4]=="Rental of aircraft":
			if payment[2]!=user:
				rentinc[0]+=payment[3]
			else:
				rentexp[0]+=payment[3]
		elif payment[4]=="Pay for assignment":
			if payment[2]!=user:
				assnmtinc[0]+=payment[3]
			else:
				assnmtexp[0]+=payment[3]
		elif payment[4]=="Crew fee":
			addcrewfee[0]+=payment[3]
		elif payment[4]=="FBO ground crew fee":
			if payment[2]!=user:
				fbogndcrew[0]+=payment[3]
			else:
				gndcrewfee[0]+=payment[3]
		elif payment[4]=="Booking Fee":
			bkgfee[0]+=payment[3]
		elif payment[4]=="Refuelling with JetA":
			if payment[2]!=user:
				fborefjet[0]+=payment[3]
			else:
				refjet[0]+=payment[3]
		elif payment[4]=="Refuelling with 100LL":
			if payment[2]!=user:
				fboref100[0]+=payment[3]
			else:
				ref100[0]+=payment[3]
		elif payment[4]=="Aircraft maintenance":
			if payment[2]!=user:
				fborepinc[0]+=payment[3]
			else:
				mxexp[0]+=payment[3]
		elif payment[4]=="Aircraft sale":
			if payment[2]!=user:
				acsold[0]+=payment[3]
			else:
				acbought[0]+=payment[3]
		elif payment[4]=="Sale of wholesale JetA":
			if payment[2]!=user:
				wsselljet[0]+=payment[3]
			else:
				wsbuyjet[0]+=payment[3]
		elif payment[4]=="Sale of wholesale 100LL":
			if payment[2]!=user:
				wssell100[0]+=payment[3]
			else:
				wsbuy100[0]+=payment[3]
		elif payment[4]=="Sale of supplies":
			if payment[2]!=user:
				wssellsupp[0]+=payment[3]
			else:
				wsbuysupp[0]+=payment[3]
		elif payment[4]=="Sale of building materials":
			if payment[2]!=user:
				wssellbld[0]+=payment[3]
			else:
				wsbuybld[0]+=payment[3]
		elif payment[4]=="Group payment":
			if payment[2]!=user:
				grpay[0]+=payment[3]
			else:
				grpay[0]-=payment[3]
		elif payment[4]=="Pilot fee":
			if payment[2]!=user:
				pltfee[0]+=payment[3]
			else:
				pltfee[0]-=payment[3]
		elif payment[4]=="Installation of equipment in aircraft":
			if payment[2]!=user:
				fboeqpinc[0]+=payment[3]
			else:
				eqinstl[0]+=payment[3]
		else:
			print("No category found for "+payment[4])

	#Income nets per category
	rent=[rentinc[0]-rentexp[0],"Rental"]
	assnmt=[assnmtinc[0]-assnmtexp[0],"Assignments"]
	ac=[acsold[0]-acbought[0],"Aircraft"]
	ws100=[fboref100[0]+wssell100[0]-wsbuy100[0],"WS 100LL"]
	wsjet=[fborefjet[0]+wsselljet[0]-wsbuyjet[0],"WS JetA"]
	fborep=[fborepinc[0]-fborepexp[0],"FBO Repairs"]
	fboeqp=[fboeqpinc[0]-fboeqpexp[0],"FBO Eqp Instl"]
	ptrent=[ptrentinc[0],"PT Rent"]
	fbo=[fbosell[0]-fbobuy[0],"FBO"]
	sup=[wssellsupp[0]-wsbuysupp[0],"Supplies"]
	bld=[wssellbld[0]-wsbuybld[0],"Building Mtrls"]
	incnets=[rent, assnmt, ac, ws100, wsjet, fborep, fboeqp, ptrent, fbo, sup, bld]
	
	#Expense nets
	#mxexp
	#ref100
	#refjet
	#bkgfee
	#gndcrewfee
	#addcrewfee
	#pltfee
	
	incnet=[]
	expnet=[ref100, refjet, bkgfee, gndcrewfee, addcrewfee, pltfee, mxexp] #Always negative
	netinc=0
	netexp=ref100[0]+refjet[0]+bkgfee[0]+gndcrewfee[0]+addcrewfee[0]+pltfee[0]+mxexp[0]
	for net in incnets: #Test if category represents an expense or income
		if net[0]>0:
			incnet.append(net)
			netinc+=net[0]
		else:
			expnet.append(net)
			netexp+=net[0]
	# revo=0
	# expo=0
	# rlabels=[]
	# rsizes=[]
	# elabels=[]
	# esizes=[]
	# for net in incnet: #Create list of labels/sizes for plot, collect small ones into "other"
		# net[0]=net[0]/netinc*100
		# if net[0]>5:
			# rlabels.append(net[1])
			# rsizes.append(net[0])
		# else:
			# revo+=net[0]
	# for net in expnet:
		# net[0]=net[0]/netexp*100
		# if net[0]>5:
			# elabels.append(net[1])
			# esizes.append(net[0])
		# else:
			# expo+=net[0]
	# if revo>0.1:
		# rsizes.append(revo)
		# rlabels.append("Other")
	# if expo>0.1:
		# esizes.append(expo)
		# elabels.append("Other")
	#pieplot(data, total, min, stitle):
	pieplot(incnet,netinc,5,"Income sources")
	pieplot(expnet,netexp,5,"Expense sources")

	#Totals income/expenses
	revs=[rentinc, assnmtinc, acsold, fboref100, fborefjet, fbogndcrew, fborepinc, fboeqpinc, ptrentinc, fbosell, wssell100, wsselljet, wssellbld, wssellsupp]
	exps=[rentexp, assnmtexp, pltfee, addcrewfee, gndcrewfee, bkgfee, ref100, refjet, mxexp, eqinstl, acbought, fborepexp, fboeqpexp, fbobuy, wsbuy100, wsbuyjet, wsbuybld, wsbuysupp]
	# rev=0
	# exp=0
	# for this in revs:
		# rev+=this[0]
	# for this in exps:
		# exp+=this[0]
	# for this in revs:
		# this[0]=this[0]/rev*100
	# for this in exps:
		# this[0]=this[0]/exp*100
	# revo=0
	# expo=0
	# rlabels=[]
	# rsizes=[]
	# elabels=[]
	# esizes=[]
	# for this in revs:
		# if this[0] < 5:
			# revo+=this[0]
		# else:
			# rlabels.append(this[1])
			# rsizes.append(this[0])
	# for this in exps:
		# if this[0] < 5:
			# expo+=this[0]
		# else:
			# elabels.append(this[1])
			# esizes.append(this[0])
	# if revo>0.1:
		# rlabels.append("Other")
		# rsizes.append(revo)
	# if expo>0.1:
		# elabels.append("Other")
		# esizes.append(expo)
	pieplot(revs,None,5,"Revenues")
	pieplot(exps,None,5,"Expenses")
	
def sumacpayments(conn,fdate,tdate): #Plot revenue portion by aircraft
	c=getpaydbcon(conn)
	d=getpaydbcon(conn)
	#Income
	rentinc=[[],"Rental income"]
	assnmtinc=[[],"Assignment income"]
	acsold=[[],"Aircraft sold"]
	fboref100=[[],"100LL pumped"]
	fborefjet=[[],"JetA pumped"]
	fbogndcrew=[[],"Ground crew income"]
	fborepinc=[[],"Repair income"]
	fboeqpinc=[[],"Eqp instl income"]
	ptrentinc=[[],"PT rent income"]
	fbosell=[[],"FBO sold"]
	wssell100=[[],"100LL sold"]
	wsselljet=[[],"JetA sold"]
	wssellbld=[[],"Building materials sold"]
	wssellsupp=[[],"Supplies sold"]
	grpay=[[],"Group payment"]
	
	#Expenses
	rentexp=[[],"Rental expense"]
	assnmtexp=[[],"Assignment expense"]
	pltfee=[[],"Pilot fees"]
	addcrewfee=[[],"Additional crew fee"]
	gndcrewfee=[[],"Ground crew fee"]
	bkgfee=[[],"Booking fee"]
	ref100=[[],"100LL pumped"]
	refjet=[[],"JetA pumped"]
	mxexp=[[],"Maintenance"]
	eqinstl=[[],"Equipment installed"]
	acbought=[[],"Aircraft bought"]
	fborepexp=[[],"FBO repair cost"]
	fboeqpexp=[[],"FBO eqp instl"]
	fbobuy=[[],"FBO bought"]
	wsbuy100=[[],"100LL bought"]
	wsbuyjet=[[],"JetA bought"]
	wsbuysupp=[[],"Supplies"]
	wsbuybld=[[],"Building materials"]

	items=[rentinc,assnmtinc,acsold,fboref100,fborefjet,fbogndcrew,fborepinc,fboeqpinc,ptrentinc,fbosell,wssell100,wsselljet,wssellbld,wssellsupp,grpay,rentexp,assnmtexp,pltfee,addcrewfee,gndcrewfee,bkgfee,ref100,refjet,mxexp,eqinstl,acbought,fborepexp,fboeqpexp,fbobuy,wsbuy100,wsbuyjet,wsbuybld,wsbuysupp]
	
	user=getname()
	fromdate=fdate+" 00:01"
	todate=tdate+" 23:59"
	ac=[]
	print("Tallying payments from"+str(fdate[0])+"-"+str(fdate[1])+" to "+str(tdate[0])+"-"+str(tdate[1])+"...")
	#(date text, payto text, payfrom text, amount real, reason text, location text, aircraft text)
	for dac in c.execute('SELECT DISTINCT aircraft FROM payments WHERE date BETWEEN ? AND ? AND payto = ? AND reason = "Pay for assignment"',(fromdate,todate,user)):
		ac.append([0,dac[0]])
		for var in items:
			var[0].append(0)
		for payment in d.execute('SELECT * FROM payments WHERE date BETWEEN ? AND ? AND aircraft = ?',(fromdate,todate,dac[0])):
			if payment[4]=="Rental of aircraft":
				if payment[2]!=user:
					rent[0][i]+=payment[3]
				else:
					rent[0][i]-=payment[3]
			elif payment[4]=="Pay for assignment":
				if payment[2]!=user:
					assnmtinc[0][i]+=payment[3]
			elif payment[4]=="Crew fee":
				addcrewfee[0][i]-=payment[3]
			elif payment[4]=="FBO ground crew fee":
				if payment[2]==user:
					gndcrewfee[0][i]-=payment[3]
			elif payment[4]=="Booking Fee":
				bkgfee[0][i]-=payment[3]
			elif payment[4]=="Refuelling with JetA":
				if payment[2]==user:
					refjet[0][i]-=payment[3]
			elif payment[4]=="Refuelling with 100LL":
				if payment[2]==user:
					ref100[0][i]-=payment[3]
			elif payment[4]=="Aircraft maintenance":
				if payment[2]==user:
					mxexp[0][i]-=payment[3]
			elif payment[4]=="Aircraft sale":
				if payment[2]!=user:
					acbuy[0][i]+=payment[3]
				else:
					acbuy[0][i]-=payment[3]
			elif payment[4]=="Pilot fee":
				if payment[2]!=user:
					pltfee[0][i]+=payment[3]
				else:
					pltfee[0]-=payment[3]
			elif payment[4]=="Installation of equipment in aircraft":
				if payment[2]==user:
					eqinstl[0][i]-=payment[3]
			else:
				print("No category (for aircraft) found for "+payment[4])

	for i in range(len(ac)): #Sum up all categories for each aircraft
		for var in items:
			ac[i][0]+=var[0][i]
		i+=1
	# gtot=0
	# for thisac in ac: #Sum up all aircraft
		# gtot+=thisac[0]
	# other=0
	# labels=[]
	# sizes=[]
	# for this ac in ac:
		# thisac[0]=thisac[0]/gtot*100
		# if thisac[0]>5:
			# labels.append(thisac[1])
			# sizes.append(thisac[0])
		# else:
			# other+=thisac[0]
	# if other>0.1:
		# sizes.append(other)
		# labels.append("Other")

	pieplot(ac,None,5,"Aircraft Income")
	
def pieplot(data, total, min, stitle): #Create a pie plot
	labels=[]
	sizes=[]
	other=0
	if total is None:
		total=0
		for cat in data:
			total+=cat[0]
	for cat in data: #Convert values to a percentage of total, separate smaller categories
		cat[0]=cat[0]/total*100
		if cat[0]>min:
			labels.append(cat[1])
			sizes.append(cat[0])
		else:
			other+=cat[0]
	if other>0.1:
		sizes.append(other)
		labels.append("Other")
	# The slices will be ordered and plotted counter-clockwise.
	colors = ['yellowgreen', 'gold', 'lightskyblue', 'lightcoral']
	#explode = (0, 0.1, 0, 0) # only "explode" the 2nd slice # But I don't wanna explode...
	plt.pie(ssizes, labels=slabels, #colors=colors,
			autopct='%1.1f%%', shadow=True, startangle=90)
	plt.axis('equal') # Set aspect ratio to be equal so that pie is drawn as a circle.
	plt.title(stitle)
	plt.show()
	
def gettype(icao): #Return name of aircraft type or error if not found
	icaodict=dicts.getactypedict()
	try:
		if icao!="":
			actype=icaodict[icao]
		else:
			actype=""
		success=1
	except (KeyError,IndexError) as e:
		print("Name for code "+icao+" not found!")
		actype=""
		success=0
	return actype, success

def main(argv): #This is where the magic happens
	
	syntaxstring='pricelog.py -un -dmac <aircraft icao> -ft <YYYY-MM-DD> -lh <price>'
	try:
		opts, args = getopt.getopt(argv,"hund:m:a:c:f:t:l:i:pqsg:v:e:",["duration=","map=","average=","cheapest=","from=","to=","low=","high=","total=","percbyac=","commodity="])
	except getopt.GetoptError:
		print(syntaxstring)
		sys.exit(2)
	print("Opening database...")
	conn=sqlite3.connect('/mnt/data/XPLANE10/XSDK/forsale.db')
	tot=0
	avg=0
	low=0
	dur=0
	pay=0
	ppay=0
	spay=0
	stot=0
	lowprice=0
	highprice=99999999
	fromdate="0000-01-01"
	todate="9999-12-31"
	for opt, arg in opts:
		if opt=='-h':
			print(syntaxstring)
			sys.exit()
		elif opt=='-u':
			acforsale(conn)
		elif opt=='-n':
			totals=gettotals(conn,"None",fromdate,todate)
			plotdates([totals],"Aircraft for sale","Aircraft")
		elif opt in ("-d", "--duration"):
			durtype,dur=gettype(arg)
		elif opt in ("-m", "--map"):
			maptype,domap=gettype(arg)
			mapaclocations(conn,maptype)
		elif opt in ("-f", "--from"):
			fromdate=arg
		elif opt in ("-t", "--to"):
			todate=arg
		elif opt in ("-a", "--average"):
			avgtype,avg=gettype(arg)
		elif opt in ("-c", "--cheapest"):
			lowtype,low=gettype(arg)
		elif opt in ("-l", "--low"):
			lowprice=arg
		elif opt in ("-i", "--high"):
			highprice=arg
		elif opt in ("-p", "--payments"):
			pay=1
		elif opt in ("-q", "--plotpayments"):
			ppay=1
		elif opt in ("-s", "--sumpayments"):
			spay=1
		elif opt in ("-g", "--total"):
			tottype,tot=gettype(arg)
		elif opt in ("-v", "--percbyac"):
			sumtype,stot=gettype(arg)
		elif opt in ("-e", "--commodity"):
			mapcommo(arg)

	if pay+ppay+spay+stot>0:
		conn2=sqlite3.connect('/mnt/data/XPLANE10/XSDK/payments.db')

	if tot==1:
		totals=gettotals(conn,tottype,fromdate,todate)
		plotdates([totals],"Number of "+tottype+" for sale","Aircraft")
	
	if avg==1:
		averages=getaverages(conn,avgtype,fromdate,todate)
		plotdates([averages],"Average price for "+avgtype,"Price")
	
	if low==1:
		lows=getlows(conn,lowtype,fromdate,todate)
		plotdates([lows],"Lowest price for "+lowtype,"Price")
	
	if dur==1:
		listings=getlistings(conn,durtype,lowprice,highprice)
		durations=[]
		for listing in listings:
			duration=listings[4]-listings[3]
			durations.append((listings[2],duration))
			print(str(listings[2])+": "+str(duration))
		plotdates([durations],"Time to sell for "+durtype,"Days")
	
	if pay==1:
		year=fromdate.split('-', 2)[0]
		month=fromdate.split('-', 2)[1]
		logpaymonth(conn2,year,month)
		conn2.close()
	
	if ppay==1:
		plotpayments(conn2,fromdate,todate)

	if spay==1:
		sumpayments(conn2,fromdate,todate)
	
	if stot==1:
		sumacpayments(conn2,fromdate,todate)

	# We can also close the connection if we are done with it.
	# Just be sure any changes have been committed or they will be lost. FOREVER
	print("Finished, closing database...")
	conn.close()
	
if __name__ == "__main__":
   main(sys.argv[1:])
