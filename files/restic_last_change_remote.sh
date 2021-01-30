#!/bin/sh

server=$1
folder=$2

ftime=$(ssh $server "ls -rtnl -D '-------%s------' $folder/index" | tail -n 1 | sed 's/.*-----\([0-9]*\)-----.*/\1/g')
ctime=$(date +%s)
diff=$(( ctime - ftime ))
diff_days=$(( diff / 86400 ))

count_index=$(ssh $server "ls -1 $folder/index" | wc -l)
count_locks=$(ssh $server "ls -1 $folder/locks" | wc -l)
count_keys=$(ssh $server "ls -1 $folder/keys" | wc -l)
count_snapshots=$(ssh $server "ls -1 $folder/snapshots" | wc -l)

# 172800s == 2d; 604800s == 7d
echo "P restic_${server}_last_backup age=$diff;172800;604800 The last Restic Backup on $server was $diff_days Days ago"
echo "P restic_${server}_count index=$count_index|locks=$count_locks;2;5|keys=$count_keys|snapshots=$count_snapshots The Restic Backup on $server contains $count_index Index Files, $count_locks Locks, $count_keys Keys and $count_snapshots Snapshots"
