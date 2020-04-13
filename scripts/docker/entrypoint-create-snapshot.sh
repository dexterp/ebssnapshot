#!/usr/bin/env bash

# Create ebs snapshots for entire region
if [[ $# -ne 0 ]]; then
    exec $@
else
    ebssnap create --readtimeout 10800 --workers 2 --log INFO --region ${AWS_REGION}
fi
