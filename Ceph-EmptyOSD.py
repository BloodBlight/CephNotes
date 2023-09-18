#!/usr/bin/env python3
import sys
import json;
import subprocess;
import time;
import argparse;

OSDToEmpty = -1;


IntGB = 1073741824;


arguments = sys.argv[1:]

Usage="""
Usage:
	-EmptyOSDs=#
		Can accept a one or more OSD IDs (as an integer), comma sepperated.
		Can be used in combination with: -EmptyHost
	-EmptyHosts=#
		Can accept a one or more hosts, comma sepperated.
		Can be used in combination with: -EmptyOSD
	-DontTargetSourceHosts
		Host that cerrently owns an OSD that is being emptied will not be used as a target for any data.
	-DoNotUseOSDs=#
		Can accept a one or more OSD IDs (as an integer), comma sepperated.
		Mannually adds OSDs to the list calculated by DontTargetSourceHosts.  Because of that, it does NOT combine with DontTargetSourceHosts.
		Note: This feature is usefull if you want don't want data sent to an OSD, but also don't want to empty it for some reason...
	-MaxThreads=#
		Default is 4, up to 8 seems to be safe.  Your millage may very!
	-ShowStatus
		Shows details on what PGs are being remapped, and how far along they are.
		Note: Must also have Ceph-GetPGReplicationStatus.py script in the same folder!
		Future: I hope to add time estimations to this one day. 
Examples:

pythong3 Ceph-EmptyOSD.py 

"""


def RemoveCommon(array1, array2):
	#Removes and items from arr1 that are in arr2 and returns it as a new array.
	return [item for item in array1 if item not in array2]

def GetOSDMap():
	#Get a list of OSDs with class info:
	command = "ceph osd df --format json"
	with open("/dev/shm/tmp.OSDs", "w") as outfile:
	    subprocess.run(command.split(), stdout=outfile, stderr=subprocess.DEVNULL)
	f = open('/dev/shm/tmp.OSDs');
	js = json.load(f);
	return js['nodes'];

def GetDeviceClass(osd_map, osd_id):
	device_class = '';
	for osd in osd_map:
		if osd['id'] == osd_id:
			#print(osd);
			return osd['device_class'];


def GetPGMap():
	command = "ceph pg dump_json pgs"
	with open("/dev/shm/tmp.CephPGs", "w") as outfile:
	    subprocess.run(command.split(), stdout=outfile, stderr=subprocess.DEVNULL)
	f = open('/dev/shm/tmp.CephPGs');
	js = json.load(f);
	return js['pg_map'];

def GetRemappedCount():
	command = "ceph -s --format json"
	with open("/dev/shm/tmp.Status", "w") as outfile:
	    subprocess.run(command.split(), stdout=outfile, stderr=subprocess.DEVNULL)
	f = open('/dev/shm/tmp.Status');
	js = json.load(f);
	return js['osdmap']['num_remapped_pgs'];

def OSDPGCount(OSDsToEmpty, osd_map):
	PGsToMove = 0;
	for osd in osd_map:
		if(osd['id'] in OSDsToEmpty):
			PGsToMove += osd['pgs'];
	return PGsToMove;

def GetOSDTree():
	#Get a list of OSDs and what host they are on:
	command = "ceph osd tree --format json"
	with open("/dev/shm/tmp.OSDTree", "w") as outfile:
	    subprocess.run(command.split(), stdout=outfile, stderr=subprocess.DEVNULL)
	f = open('/dev/shm/tmp.OSDTree');
	js = json.load(f);
	return js['nodes'];


def GetOSDsOnSameHost(OSDToEmpty, osd_tree):
	#print(OSDToEmpty);
	for host in osd_tree:
		if host['type_id'] == 1:
			children = host['children'];
			#print(host);
			if OSDToEmpty in children:
				return children;


def GetOSDsOnHost(Host, osd_tree):
	#print(OSDToEmpty);
	for host in osd_tree:
		if host['type_id'] == 1:
			if host['name'].lower() == Host.lower():
				return host['children'];

def FindBusyTargets(pg_map):
	#Who is already recieving, so we don't send too much!
	#Note to self:
	#Active is our source, up is our target.
	#active+remapped+backfilling
	busytargets = [];
	for pg in pg_map['pg_stats']:
		pgid = pg['pgid'];
		up = pg['up'];
		acting = pg['acting'];
		width = len(up);
		width2 = len(acting);
		if(width != width2):
			print('EGAD!  We have a miss-matched count of "up" VS "acting" PGs on [', pgid, ']!  This usualy means something is down, and I cannot deal with that, sorry!  Bye...  :<');
			sys.exit(1)
		if pg['state'].find('remapped') != -1:
			#print("Detected remapping on:", pgid);
			for x in range(0, width):
				if(up[x] != acting[x]):
					#print("OSD", up[x], "is already a target for repliation.");
					busytargets.append(up[x]);
	return busytargets;


def FindPGToMove(pg_map, OSDToEmpty):
	#Who is already recieving, so we don't send too much!
	#We are needing to stay here (all in one function) to optimize the parsing of pg_map.  No need to burn the poor CPU up....
	for pg in pg_map['pg_stats']:
		up = pg['up'];
		if pg['state'].find('remapped') == -1:
			#print("Detected remapping on:", pg['pgid']);
			if OSDToEmpty in up:
				return pg;


def FindBestTargets(osd_map, OSDToEmpty, PGToMigrate):
	#Who is already recieving, so we don't send too much!
	#We are needing to stay here (all in one function) to optimize the parsing of pg_map.  No need to burn the poor CPU up....
	targets = [];
	device_class = GetDeviceClass(osd_map, OSDToEmpty);
	for osd in osd_map:
		osdid = osd['id'];
		if osdid not in PGToMigrate['up']:
			if(device_class == osd['device_class']):
				targets.append([osdid, osd['utilization']]);
	targets.sort(key=lambda x: x[1])
	return targets;

#Parse inputs.
def parse_osd_ids(osd_ids):
	try:
		return [int(id) for id in osd_ids.split(",")]
	except ValueError:
		raise argparse.ArgumentTypeError("Invalid OSD IDs. Must be a comma-separated list of integers.")

def parse_hosts(hosts):
	return hosts.split(",")

def parse_arguments():
	parser = argparse.ArgumentParser(description="This script is designed to empty one or more OSDs in a controlled way, preventing slow IOPs.")
	parser.add_argument("-EmptyOSDs", type=parse_osd_ids, default=[], metavar="#", help="One or more OSD IDs (as an integer), comma separated.")
	parser.add_argument("-EmptyHosts", type=parse_hosts, default=[], metavar="#", help="One or more hosts, comma separated.")
	parser.add_argument("-DontTargetSourceHosts", action="store_true", help="No host that currently owns a OSD that is being emptied will not be used as a target.")
	parser.add_argument("-DoNotUseOSDs", type=parse_osd_ids, default=[], metavar="#", help="One or more OSD IDs (as an integer), comma separated.")
	parser.add_argument("-MaxThreads", type=int, default=4, metavar="#", help="Default is 4, up to 8 seems to be safe.")
	parser.add_argument("-ShowStatus", action="store_true", help="!NOT IMPLEMENTED! Shows details on what PGs are being remapped, and how far along they are.")
	return parser.parse_args()

args = parse_arguments()

if len(arguments) == 0:
	print(Usage);
	sys.exit(1)
	

#OSDToEmpty = 1

# Threads total?  Threads per OSD?  Think on it...
#Threads = arguments[1];

#NoTargetsOnHost = True;

#DoNotUseOSDs = [];
print('########################## ! NOTICE ! ##########################');
print('# This script can be stopped and restarted at any time.        #');
print('# DO NOT run multiple copies at once.  Bad things!             #');
print('################################################################');
print('');
print('Loading...');
# Build out what we want to do.
osd_map = GetOSDMap();
osd_map = GetOSDMap();
pg_map = GetPGMap();
osd_tree = GetOSDTree();

OSDsToEmpty = []
DoNotUseOSDs = []

for OSD in args.EmptyOSDs:
	OSDsToEmpty.append(OSD)
	DoNotUseOSDs.append(OSD)

for OSD in args.DoNotUseOSDs:
	DoNotUseOSDs.append(OSD)

if args.DontTargetSourceHosts:
	for OSD in args.EmptyOSDs:
		HostOSDs = GetOSDsOnSameHost(OSD, osd_tree);
		for HostOSD in HostOSDs:
			DoNotUseOSDs.append(HostOSD)

for Host in args.EmptyHosts:
	HostOSDs = GetOSDsOnHost(Host, osd_tree);
	for HostOSD in HostOSDs:
		OSDsToEmpty.append(HostOSD)
		DoNotUseOSDs.append(HostOSD)


OSDsToEmpty = list(set(sorted(OSDsToEmpty)));
DoNotUseOSDs = list(set(sorted(DoNotUseOSDs)));
print('');
print('##########################  The Plan  ##########################');
print('Will empty these OSDs:', OSDsToEmpty);
print('Will NOT use these OSDs:', DoNotUseOSDs);
print('################################################################');
#time.sleep(3)


#Exit
#sys.exit(1)


#Prime the loop...
PGsLeft = OSDPGCount(OSDsToEmpty, osd_map);
LastMessage = '';

#If we get into a situation where all possible targets are being used, this will keep the script from doing too much extra work:
OSDLimitHit = False;

#Note to self:
#Active is our source, up is our target.
#active+remapped+backfilling

strWarning = '';
while PGsLeft > 0:
	#Main Loop
	CurrentThreads = GetRemappedCount();
	
	Message = 'There are currently ' + str(CurrentThreads) + ' of a maximum of ' + str(args.MaxThreads) + ' remaps running with ' + str(PGsLeft) + ' remaining.';
	if LastMessage != Message:
		#sys.stdout.write();
		#sys.stdout.flush()
		print(Message);
		LastMessage = Message;

		#Don't try if not needed.
		if CurrentThreads < args.MaxThreads:
			RemapsDone = 0;
			for OSDToEmpty in OSDsToEmpty:
				#Need to re-check to make sure to stop when needed.
				if CurrentThreads < args.MaxThreads:
					# Load updated maps.
					osd_map = GetOSDMap();
					pg_map = GetPGMap();
					osd_tree = GetOSDTree();
					PGsLeft = OSDPGCount(OSDsToEmpty, osd_map);
					
					#Find PG to migrate:
					PGToMigrate = FindPGToMove(pg_map, OSDToEmpty);
					
					# Find all targets sorted by free space:
					TargetsWithUtilization = FindBestTargets(osd_map, OSDToEmpty, PGToMigrate);
					
					#Trimming this down for easy coding later, just don't want to toss the data for usilization yet.  Might be usefull later..
					targets = [element[0] for element in TargetsWithUtilization];


					# Remove all busy migration targets.
					targets = RemoveCommon(targets, FindBusyTargets(pg_map));
					
					# Remove targets on do-not-use list.
					targets = RemoveCommon(targets, DoNotUseOSDs);
					
					# OPTIONAL: Remove targets on the same host.
					if args.DontTargetSourceHosts:
						targets = RemoveCommon(targets, GetOSDsOnSameHost(OSDToEmpty, osd_tree));

					#Can we do it?
					pgid = PGToMigrate['pgid'];
					if len(targets) > 0:
						print('Lets move', pgid, 'from OSD', OSDToEmpty, 'to', targets[0]);
						command = 'ceph osd pg-upmap-items '
						command += pgid
						command += ' '
						command += str(OSDToEmpty)
						command += ' '
						command += str(targets[0])
						print(command);
						subprocess.run(command.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
						RemapsDone += 1;
					else:
						print('WARNING!  Cannot find a place to move the pg [', pgid, '], but there are active remaps...');
						print('Will attempt again later...');
						
					# Wait a few seconds, let ceph do its thing.
					time.sleep(5)
					
					#I COULD reload this value, rather than just adding 1, but JUST INCASE things aren't going quick enough, I don't want to go into a loop!
					CurrentThreads += 1;

			if RemapsDone == 0:
				if CurrentThreads == 0:
					print('Could not start any remaps...  Exiting!');
					sys.exit(1)
	if PGsLeft > 0:
		time.sleep(30)
		print('Sleeping...');

