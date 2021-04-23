#!/bin/bash

set -eux

while getopts s:r:m: flag
do
    case "${flag}" in
        s) sender=${OPTARG};;
        r) receiver=${OPTARG};;
        m) message=${OPTARG};;
    esac
done

signal-cli \
  --verbose \
  --config /project/config \
  --username "${sender}" \
  send \
  --message "${message}" \
  "${receiver}"