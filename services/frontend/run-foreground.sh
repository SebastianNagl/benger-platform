#!/bin/bash
set -m  # Enable job control
trap '' TSTP  # Ignore SIGTSTP
exec npx next dev