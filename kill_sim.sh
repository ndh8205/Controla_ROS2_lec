#!/bin/bash
pkill -9 -f "gz sim" 2>/dev/null
pkill -9 -f "parameter_bridge" 2>/dev/null
pkill -9 -f "web_video_server" 2>/dev/null
pkill -9 -f "rosbridge" 2>/dev/null
pkill -9 -f "chief_propagator" 2>/dev/null
sleep 1
echo "ALL CLEAN"
