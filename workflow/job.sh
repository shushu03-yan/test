#!/bin/bash
#SBATCH --job-name=int1_hvf
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:10:00
#SBATCH --output=/gpfs/work/che/qitaiwu23/shushu/raspa/runs/void_fraction/int1_hvf_298k_smoke_v2/logs/slurm_%j.out
#SBATCH --error=/gpfs/work/che/qitaiwu23/shushu/raspa/runs/void_fraction/int1_hvf_298k_smoke_v2/logs/slurm_%j.err

set -euo pipefail
cd /gpfs/work/che/qitaiwu23/shushu/raspa/runs/void_fraction/int1_hvf_298k_smoke_v2/task
module load raspa2
echo "Job started on ${HOSTNAME:-unknown}"
simulate simulation.input
echo "Job finished"
