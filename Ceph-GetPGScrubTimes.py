#!/usr/bin/env python3

import sys;
import json;
import subprocess;
import datetime;
import pytz;
from collections import defaultdict
import rados

#conffile='/etc/ceph/ceph.conf'

def generate_histogram(scrub_times):
    histogram = defaultdict(int)
    for scrub_time in scrub_times:
        histogram[scrub_time.strftime("%B %d, %Y")] += 1
    return histogram


def print_histogram(histogram):
	for date, count in sorted(histogram.items(), key=lambda x: datetime.datetime.strptime(x[0], "%B %d, %Y")):
		print(date + ": " + "*" * count + " ({})".format(count))
        
#pg_map
#  pg_stats
#    pgid
#    up
#    acting
#    last_scrub_stamp
IntGB = 1073741824;


#Lets get our JSON data, as it isn't avalible from the rados module (!please correct me if I am wrong!).
command = "ceph pg dump_json pgs"
result = subprocess.run(command.split(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

if result.returncode == 0:
    json_output = result.stdout.decode('utf-8')
    js = json.loads(json_output)
    # Continue with processing the json data as needed

#Lets build a list of pools first.
#pg_map
#  pool_stats
#    poolid


pg_map = js['pg_map'];

#Need to include the UTC here:
now = datetime.datetime.now(pytz.utc);

#Lets connect to the cluster and start building a list of pools:
cluster = rados.Rados(conffile='/etc/ceph/ceph.conf')
cluster.connect()

pools = cluster.list_pools()

ceph_pools = []
for pool in pools:
	pool_id = cluster.pool_lookup(pool)
	ceph_pools.append([pool_id, pool])
	
cluster.shutdown()

#Math time.
for pool in ceph_pools:
	oldest = now;
	total=0;
	inlastday=0;
	scrub_times=[];
	#pg_map = js['pg_map'];
	for pg_stats in pg_map['pg_stats']:
		pgid = pg_stats['pgid'];
		pool_id = str(pool[0]);
		if pgid.split(".")[0] == pool_id:
			last_scrub_stamp = pg_stats['last_scrub_stamp']; 
			dt = datetime.datetime.strptime(last_scrub_stamp, '%Y-%m-%dT%H:%M:%S.%f%z');
			if oldest > dt:
				oldest = dt;
			message = pgid + ',' + dt.strftime("%Y-%m-%d %H:%M:%S");
			#print(message);
			
			scrub_times.append(dt)
			
			total += 1;
			diff = now - dt;
			
			if diff.total_seconds() <= 24 * 3600:
				inlastday += 1;
		
	print('### Pool:', pool[1], ' (ID:', pool[0], ') ####')
	
	if inlastday == 0:
		print('## WARNING: No PGs have been scrubbed for over 24 hours for this pool! ##')
	else:
		ETC = now + datetime.timedelta(seconds=(((total - inlastday) / inlastday) * 24 * 3600));
		oldest_string = oldest.strftime("%Y-%m-%d %H:%M:%S");

		Hours = round(((total - inlastday) / inlastday + 1) * 24, 1);

		print('# There are', total, 'PGs, and', inlastday, 'have been scrubbed in the last 24 hours.  At this rate, all PGs should be scrubbed by', ETC.strftime("%Y-%m-%d %H:%M:%S"), ' It should be possible to complete a full scrub in', Hours, 'hours.  The oldest PG scrub is:', oldest_string);
	
	print('');
	print('#Here is a histogram of scrub times:');
	print_histogram(generate_histogram(scrub_times))
	print('');
	
