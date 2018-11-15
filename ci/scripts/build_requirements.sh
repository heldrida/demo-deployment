#!/usr/bin/env bash
apt-get update
apt-get install -y python-dev python-pip jq bsdmainutils dnsutils envsubst
pip install awscli
