#!/usr/bin/env python3

import sys, json;
import subprocess
#pg_map
#  pg_stats
#    pgid
#    up
#    acting
IntGB = 1073741824;


# Define the command
command = "ceph pg dump_json pgs"

# Execute the command and redirect output to /dev/shm/tmp.CephPGs and redirect error to /dev/null
with open("/dev/shm/tmp.CephPGs", "w") as outfile:
    subprocess.run(command.split(), stdout=outfile, stderr=subprocess.DEVNULL)


f = open('/dev/shm/tmp.CephPGs');
js = json.load(f);
pg_map = js['pg_map'];
#pg_stats = pg_map['pg_stats'];
found=0

for pg_stats in pg_map['pg_stats']:
	pgid = pg_stats['pgid'];
	state = pg_stats['state'];
	if('clean' not in state):	
		found = 1;
		stat_sum = pg_stats['stat_sum'];
		num_bytes = stat_sum['num_bytes'];
		num_objects = stat_sum['num_objects'];
		num_objects_misplaced = stat_sum['num_objects_misplaced'];
		up = pg_stats['up'];
		acting = pg_stats['acting'];
		width=len(up)
		misplaced_ratio = float(num_objects_misplaced) / (float(num_objects) * width);
		#print('Debug: num_bytes =', num_bytes, 'num_objects_misplaced =', num_objects_misplaced, 'num_objects =', num_objects, 'width =', width, 'misplaced_ratio =', misplaced_ratio);
		
		gbs = float(int(num_bytes / 1024 / 1024 / 1024 * misplaced_ratio * 10)) / 10 ;
		source = [];
		target = [];
		hits = 0;

		for x in range(1, width + 1):
			if(up[x-1] != acting[x-1]):
				hits += 1;
				source.append(acting[x-1])
				target.append(up[x-1])
		print(pg_stats['pgid'], state, "- Left:", int(num_bytes * misplaced_ratio), "(GBs:", str(gbs * hits) + ') - Pools:', source, '-->', target, '-', round(misplaced_ratio*100,1),'%');

if(found == 0):
	print('No out of place PGs found.');
