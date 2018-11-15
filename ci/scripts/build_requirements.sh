#!/usr/bin/env bash
apt-get update
apt-get install -y python-dev python-pip jq bsdmainutils dnsutils gettext-base
pip install --upgrade pip
pip install awscli
