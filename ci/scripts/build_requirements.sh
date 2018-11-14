#!/usr/bin/env bash
apt-get update
apt-get install -y python-dev jq bsdmainutils dnsutils
curl -O https://bootstrap.pypa.io/get-pip.py | python get-pip.py
pip install awscli
