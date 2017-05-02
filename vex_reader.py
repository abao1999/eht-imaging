# Read in .vex files. and function to observe them
# Assumes there is only 1 MODE in vex file
# Hotaka Shiokawa - 2017

import vlbi_imaging_utils as vb
import numpy as np
import re
import jdcal
import movie_utils as mu

def movie_observe_vex(movie, vex, source, synchronize_start = True, t_int = 0.0, sgrscat=False, add_th_noise=True, opacitycal=True, ampcal=True, phasecal=True, frcal=True,
                tau=vb.TAUDEF, gainp=vb.GAINPDEF, gain_offset=vb.GAINPDEF, dtermp=vb.DTERMPDEF,
                jones=False, inv_jones=False, dcal=True):
    """Generates an observation corresponding to a given vex objectS
       movie is a movie object 
       vex is a vex object
       source is the source string identifier in the vex object, e.g., 'SGRA'
       synchronize_start is a flag that determines whether the start of the movie should be defined to be the start of the observations
       t_int overrides the vex scans to produce visibilities for each t_int seconds
    """

    obs_List=[]

    if synchronize_start:
        movie = movie.copy()
        movie.mjd = vex.sched[0]['mjd_floor']
        movie.start_hr = vex.sched[0]['start_hr']

    movie_start = float(movie.mjd) + movie.start_hr/24.0
    movie_end   = movie_start + len(movie.frames)*movie.framedur/24.0/3600.0

    print "Movie MJD Range: ",movie_start,movie_end

    snapshot = 1.0
    if t_int > 0.0: 
        snapshot = 0.0

    for i_scan in range(len(vex.sched)):
        if vex.sched[i_scan]['source'] != source:
            continue
        subarray = vb.make_subarray(vex.array, [vex.sched[i_scan]['scan'][key]['site'] for key in vex.sched[i_scan]['scan'].keys()])

        if snapshot == 1.0:
            t_int = np.max(np.array([vex.sched[i_scan]['scan'][site]['scan_sec'] for site in vex.sched[i_scan]['scan'].keys()]))
            print t_int
            #vex.sched[i_scan]['scan'][0]['scan_sec']

        vex_scan_start_mjd = float(vex.sched[i_scan]['mjd_floor']) + vex.sched[i_scan]['start_hr']/24.0
        vex_scan_stop_mjd  = vex_scan_start_mjd + vex.sched[i_scan]['scan'][0]['scan_sec']/3600.0/24.0

        print "Scan MJD Range: ",vex_scan_start_mjd,vex_scan_stop_mjd

        if vex_scan_start_mjd < movie_start or vex_scan_stop_mjd > movie_end:
            continue

        obs = subarray.obsdata(movie.ra, movie.dec, movie.rf, vex.bw_hz, t_int, t_int, 
                                   vex.sched[i_scan]['start_hr'], vex.sched[i_scan]['start_hr'] + vex.sched[i_scan]['scan'][0]['scan_sec']/3600.0 - vb.EP, 
                                   mjd=vex.sched[i_scan]['mjd_floor'],
                                   elevmin=.01, elevmax=89.99, timetype='UTC')   
        obs_List.append(obs)

    if len(obs_List) == 0:
        raise Exception("Movie has no overlap with the vex file and source=" + source) 

    obs = vb.merge_obs(obs_List)

    return movie.observe_same(obs, sgrscat=sgrscat, add_th_noise=add_th_noise, opacitycal=opacitycal,
                                ampcal=ampcal, gainp=gainp, phasecal=phasecal, gain_offset=gain_offset, 
                                jones=jones, inv_jones=inv_jones, dcal=dcal, dtermp=dtermp, frcal=frcal,
                                repeat=False)   

def observe_vex(im, vex, source, sgrscat=False, add_th_noise=True, opacitycal=True, ampcal=True, phasecal=True, frcal=True,
                tau=vb.TAUDEF, gainp=vb.GAINPDEF, gain_offset=vb.GAINPDEF, dtermp=vb.DTERMPDEF,
                jones=False, inv_jones=False, dcal=True):
    """Generates an observation corresponding to a given vex object
       im is an image
       vex is a vex object
       source is the source string identifier in the vex object, e.g., 'SGRA'
    """

    obs_List=[]
    for i_scan in range(len(vex.sched)):
        if vex.sched[i_scan]['source'] != source:
            continue
        subarray = vb.make_subarray(vex.array, [vex.sched[i_scan]['scan'][key]['site'] for key in vex.sched[i_scan]['scan'].keys()])

        obs = im.observe(subarray, vex.sched[i_scan]['scan'][0]['scan_sec'], 2.0*vex.sched[i_scan]['scan'][0]['scan_sec'], 
                                   vex.sched[i_scan]['start_hr'], vex.sched[i_scan]['start_hr'] + vex.sched[i_scan]['scan'][0]['scan_sec']/3600.0, 
                                   vex.bw_hz, mjd=vex.sched[i_scan]['mjd_floor'],
                                   elevmin=.01, elevmax=89.99)    
        obs_List.append(obs)

    return vb.merge_obs(obs_List)

class Vex(object):

    def __init__(self, filename):

        f = open(filename)
        raw = f.readlines()
        f.close()

	self.filename = filename

        # Divide 'raw' data into sectors of '$' marks
        # ASSUMING '$' is the very first character in a line (no space in front)
        metalist = [] # meaning list of metadata

        for i in range(len(raw)):
            if raw[i][0]=='$':
                temp = [raw[i]]
                break

        for j in range(i+1,len(raw)):
            if raw[j][0]!='$':
                temp.append(raw[j])
            elif raw[j][0]=='$':
                metalist.append(temp)
                temp = [raw[j]]
            else:
                print 'Something is wrong.'
        metalist.append(temp) # don't forget to add the final one
        self.metalist = metalist


        # Extract desired information
        # SOURCE ========================================================
        SOURCE = self.get_sector('SOURCE')
        source = []
        indef = False
 
        for i in range(len(SOURCE)):
 
            line = SOURCE[i]
            if line[0:3]=="def":
                indef=True
 
            if indef:
                ret = self.get_variable("source_name",line)
                if len(ret)>0: source_name = ret
                ret = self.get_variable("ra",line)
                if len(ret)>0: ra = ret
                ret = self.get_variable("dec",line)
                if len(ret)>0: dec = ret
                ret = self.get_variable("ref_coord_frame",line)
                if len(ret)>0: ref_coord_frame = ret
 
                if line[0:6]=="enddef":
                    source.append({'source':source_name,'ra':ra,'dec':dec,'ref_coord_frame':ref_coord_frame})
                    indef=False
 
        self.source = source


        # FREQ ==========================================================
	FREQ = self.get_sector('FREQ')
        indef = False

	nfreq = 0
	for i in range(len(FREQ)):

            line = FREQ[i]
            if line[0:3]=="def":
		if nfreq>0: print "Not implemented yet."
		nfreq += 1
		indef=True

            if indef:
                idx = line.find('chan_def')
                if idx>=0 and line[0]!='*':
                     chan_def = re.findall("[-+]?\d+[\.]?\d*",line)
                     self.freq = float(chan_def[0])*1.e6
                     self.bw_hz = float(chan_def[1])*1.e6

                if line[0:6]=="enddef": indef=False


        # SITE ==========================================================
        SITE = self.get_sector('SITE')
        sites = []
        site_ID_dict = {}
        indef = False

        for i in range(len(SITE)):
 
            line = SITE[i]
            if line[0:3]=="def": indef=True
 
            if indef:
                # get site_name and SEFD
                ret = self.get_variable("site_name",line)
                if len(ret)>0:
                    site_name = ret
                    SEFD = self.get_SEFD(site_name)
 
                # making dictionary of site_ID:site_name
                ret = self.get_variable("site_ID",line)
                if len(ret)>0:
                    site_ID_dict[ret] = site_name
 
                # get site_position
                ret = self.get_variable("site_position",line)
                if len(ret)>0:
                    site_position = re.findall("[-+]?\d+[\.]?\d*",line)
 
                # same format as Andrew's array tables
                if line[0:6]=="enddef":
                    sites.append([site_name,site_position[0],site_position[1],site_position[2],SEFD])
                    indef=False

 
        # Construct Array() object of Andrew's format
        # mimic the function "load_array(filename)"
        tdataout = [np.array((x[0],float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[4]),0.0, 0.0, 0.0, 0.0, 0.0),
                               dtype=vb.DTARR) for x in sites]
        tdataout = np.array(tdataout)

	self.array = vb.Array(tdataout)


        # SCHED  =========================================================
        SCHED = self.get_sector('SCHED')
        sched = []
        inscan = False
 
        for i in range(len(SCHED)):
 
            line = SCHED[i]
            if line[0:4]=="scan":
                inscan=True
                temp={}
		temp['scan']={}
		cnt = 0
 
            if inscan:
                ret = self.get_variable("start",line)
                if len(ret)>0:
                    mjd,hr = self.vexdate_to_MJD_hr(ret) # convert vex time format to mjd and hour
                    temp['mjd_floor'] = mjd
                    temp['start_hr'] = hr

                ret = self.get_variable("mode",line)
                if len(ret)>0: temp['mode'] = ret
 
                ret = self.get_variable("source",line)
                if len(ret)>0: temp['source'] = ret
 
                ret = self.get_variable("station",line)
                if len(ret)>0:
                    site_ID = ret
                    site_name = site_ID_dict[site_ID] # convert to more familier site name
                    sdur = re.findall("[-+]?\d+[\.]?\d*",line)
                    s_st = float(sdur[0]) # start time in sec
                    s_en = float(sdur[1]) # end time in sec
                    d_size = float(sdur[2]) # data size(?) in GB
                    temp['scan'][cnt] = {'site':site_name,'scan_sec_start':s_st,'scan_sec':s_en,'data_size':d_size}
                    cnt +=1
 
                if line[0:7]=="endscan":
                    sched.append(temp)
                    inscan=False

        self.sched = sched 


    # Function to obtain a desired sector from 'metalist'
    def get_sector(self, sname):
        for i in range(len(self.metalist)):
            if sname in self.metalist[i][0]:
                return self.metalist[i]
        print 'No sector named %s'%sname
        return False

    # Function to get a value of 'vname' in a line which has format of
    # 'vname' = value ;(or :)
    def get_variable(self, vname, line):
        idx = line.find(vname)
        name = ''
        if idx>=0 and line[0]!='*':
            start = False
            for i in range(idx+len(vname),len(line)):
                if start==True:
                    if line[i]==';' or line[i]==':': break
                    elif line[i]!=' ': name += line[i]
                if start==False and line[i]!=' ' and line[i]!='=': break
                if line[i]=='=': start = True
        return name

    # Find SEFD for a given station name.
    # For now look for it in Andrew's tables
    # Vex files could have SEFD sector.
    def get_SEFD(self, station):
        f = open(os.path.dirname(os.path.abspath(__file__)) + "/arrays/SITES.txt")
        sites = f.readlines()
        f.close()
        for i in range(len(sites)):
            if sites[i].split()[0]==station:
                return float(re.findall("[-+]?\d+[\.]?\d*",sites[i])[3])
        print 'No station named %s'%station
        return 10000. # some arbitrary value

    # Function to find MJD (int!) and hour in UT from vex format,
    # e.g, 2016y099d05h00m00s
    def vexdate_to_MJD_hr(self, vexdate):
        time = re.findall("[-+]?\d+[\.]?\d*",vexdate)
        year = int(time[0])
        date = int(time[1])
        mjd = jdcal.gcal2jd(year,1,1)[1]+date-1
        hour = int(time[2]) + float(time[3])/60. + float(time[4])/60./60.
        return mjd,hour
