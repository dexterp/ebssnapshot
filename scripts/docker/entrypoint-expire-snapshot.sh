#!/usr/bin/env bash

# Expire ebs snapshot for entire region
if [[ $# -ne 0 ]]; then
    exec $@
else
    ebssnap expire --readtimeout 10800 --workers 4 --log INFO --region ${AWS_REGION} --inlife "-7"
fi
