#!/usr/bin/env python3
import os
import sys
import subprocess
import json
import statistics
import datetime
import requests
from pathlib import Path
import multiprocessing
import argparse

# Configuration
CONFIG = {
    'test_container': 'docker.io/huggingface/transformers-all-latest-torch-nightly-gpu:latest',
    'iterations': 5,
    'build_dir': './snapshot',
    'results_dir': './results',
    'binary_path': 'snapshot/linux-build_linux_amd64_v1/syft',
    'platform': 'linux/amd64',
    'current_run': 0
}

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Measure Syft performance across versions')
    parser.add_argument('--pr', help='PR branch to test against main (e.g. feat/parallelize-file-hashing)')
    return parser.parse_args()

def setup_environment():
    """Configure environment variables and create necessary directories."""
    cpu_count = multiprocessing.cpu_count()
    os.environ['SYFT_PARALLELISM'] = str(cpu_count * 2)
    os.environ['SYFT_CHECK_FOR_APP_UPDATE'] = 'false'
    
    for directory in [CONFIG['build_dir'], CONFIG['results_dir']]:
        Path(directory).mkdir(exist_ok=True)

def get_log_path(commit_id, run_number):
    """Generate unique log file path for each run."""
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    log_dir = Path(CONFIG['results_dir']) / 'logs'
    log_dir.mkdir(exist_ok=True)
    return log_dir / f"syft_{commit_id}_run{run_number}_{timestamp}.log"

def test_pr_performance(pr_branch):
    """Test performance between main and a PR branch."""
    build_path = Path(CONFIG['build_dir'])
    
    # Ensure we have the latest main
    subprocess.run(['git', 'fetch', 'origin', 'main'], cwd=build_path, check=True)
    subprocess.run(['git', 'checkout', 'main'], cwd=build_path, check=True)
    subprocess.run(['git', 'pull'], cwd=build_path, check=True)
    
    # Test main first
    subprocess.run(['make', 'build'], cwd=build_path, check=True)
    main_results = run_performance_test('main')
    
    # Now test PR branch
    subprocess.run(['git', 'fetch', 'origin', pr_branch], cwd=build_path, check=True)
    subprocess.run(['git', 'checkout', pr_branch], cwd=build_path, check=True)
    subprocess.run(['make', 'build'], cwd=build_path, check=True)
    pr_results = run_performance_test(pr_branch)
    
    return main_results, pr_results

def cache_container_image(binary_path):
    """Run syft once to cache the container image."""
    print(f"[info] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Caching container image")
    subprocess.run([
        str(binary_path),
        '--platform', CONFIG['platform'],
        CONFIG['test_container'],
        '-o', 'syft-json=/dev/null'
    ], check=True)

def get_commits_after_tag(tag):
    """Get list of commits after the specified tag in chronological order."""
    build_path = Path(CONFIG['build_dir'])
    
    # Get the commit hash for the tag
    tag_hash = subprocess.check_output(
        ['git', 'rev-list', '-n', '1', tag],
        cwd=build_path
    ).decode().strip()
    
    # Get all commits after the tag in chronological order
    commits_output = subprocess.check_output(
        ['git', 'log', '--reverse', '--format=%H %s', f'{tag_hash}..main'],
        cwd=build_path
    ).decode()
    
    # Parse commits into list of (hash, subject) tuples
    commits = []
    for line in commits_output.splitlines():
        if line:
            full_hash, subject = line.split(' ', 1)
            short_hash = full_hash[:7]
            commits.append((short_hash, full_hash, subject))
    
    return commits

def get_latest_release():
    """Get the latest Syft release version from GitHub API."""
    response = requests.get('https://api.github.com/repos/anchore/syft/releases/latest')
    response.raise_for_status()
    return response.json()['tag_name']

def clone_and_build(version):
    """Clone specific version of Syft and build it."""
    build_path = Path(CONFIG['build_dir'])
    
    # Clone repository if not exists
    if not (build_path / '.git').exists():
        subprocess.run(['git', 'clone', 'https://github.com/anchore/syft.git', str(build_path)], check=True)
    
    # Checkout version and build
    subprocess.run(['git', 'checkout', version], cwd=build_path, check=True)
    subprocess.run(['make', 'build'], cwd=build_path, check=True)

def run_syft_test():
    """Run a single Syft test and return execution time in seconds."""
    binary = Path(CONFIG['build_dir']) / CONFIG['binary_path']
    
    if not binary.exists():
        raise FileNotFoundError(f"Syft binary not found at {binary}")
    
    # Get commit ID from current git HEAD
    commit_id = subprocess.check_output(
        ['git', 'rev-parse', '--short', 'HEAD'],
        cwd=CONFIG['build_dir']
    ).decode().strip()
    
    print(f"[info] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Start run {CONFIG['current_run']} for commit {commit_id}")
    
    start_time = datetime.datetime.now()
    
    # Create log file
    log_path = get_log_path(commit_id, CONFIG['current_run'])
    with open(log_path, 'w') as log_file:
        subprocess.run([
            str(binary),
            '-v',  # Add verbose logging
            '--platform', CONFIG['platform'],
            CONFIG['test_container'],
            '-o', 'syft-json=/dev/null'
        ], check=True, stdout=log_file, stderr=subprocess.STDOUT)
    
    end_time = datetime.datetime.now()
    print(f"[info] {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} End run {CONFIG['current_run']} for commit {commit_id}")
    
    return (end_time - start_time).total_seconds()

def get_syft_env_vars():
    """Get all environment variables that start with SYFT_"""
    return {k: v for k, v in os.environ.items() if k.startswith('SYFT_')}

def run_performance_test(version):
    """Run multiple iterations of Syft test and calculate statistics."""
    times = []
    CONFIG['current_run'] = 0  # Initialize run counter
    
    for i in range(CONFIG['iterations']):
        CONFIG['current_run'] = i + 1  # Update run number
        try:
            execution_time = run_syft_test()
            times.append(execution_time)
        except subprocess.CalledProcessError as e:
            print(f"Error running test: {e}")
            continue
    
    return {
        'min': min(times),
        'max': max(times),
        'avg': statistics.mean(times)
    }

def append_to_report(report_path, version, results, is_first=False, commit_desc=None):
    """Append results to the report file."""
    if is_first:
        header = [
            f"# Syft Performance Test Results\n",
            f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Container: {CONFIG['test_container']}",
            f"Environment Variables:"
        ]
        
        syft_vars = get_syft_env_vars()
        for var, value in sorted(syft_vars.items()):
            header.append(f"- {var}={value}")
        
        header.extend([
            f"\n## Results\n",
            "| Version/Description | Commit | Min (s) | Max (s) | Avg (s) |",
            "|-------------------|--------|---------|---------|---------|"
        ])
        report_path.write_text('\n'.join(header) + '\n')
    
    with report_path.open('a') as f:
        if isinstance(results, dict) and 'full_hash' in results:
            commit_link = f"[{version}](https://github.com/anchore/syft/commit/{results['full_hash']})"
            f.write(f"| {commit_desc} | {commit_link} | {results['min']:.2f} | {results['max']:.2f} | {results['avg']:.2f} |\n")
        else:
            f.write(f"| {version} | - | {results['min']:.2f} | {results['max']:.2f} | {results['avg']:.2f} |\n")


def main():
    try:
        args = parse_arguments()
        setup_environment()
        
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
        report_path = Path(CONFIG['results_dir']) / f"results_{timestamp}.md"
        
        # Initial clone and build of latest release to get a working binary
        version = get_latest_release()
        clone_and_build(version)
        binary = Path(CONFIG['build_dir']) / CONFIG['binary_path']
        
        # Cache container image once at start
        cache_container_image(binary)
        
        if args.pr:
            print(f"Testing PR branch: {args.pr}")
            build_path = Path(CONFIG['build_dir'])
            
            # Test main
            subprocess.run(['git', 'checkout', 'main'], cwd=build_path, check=True)
            subprocess.run(['make', 'build'], cwd=build_path, check=True)
            main_results = run_performance_test('main')
            
            # Test PR
            subprocess.run(['git', 'checkout', args.pr], cwd=build_path, check=True)
            subprocess.run(['make', 'build'], cwd=build_path, check=True)
            pr_results = run_performance_test(args.pr)
            
            append_to_report(report_path, 'main', main_results, is_first=True)
            append_to_report(report_path, args.pr, pr_results)
        else:
            results = run_performance_test(version)
            append_to_report(report_path, version, results, is_first=True)
            
            commits = get_commits_after_tag(version)
            print(f"Found {len(commits)} commits after {version}")
            
            for short_hash, full_hash, subject in commits:
                print(f"\nTesting commit: {short_hash} - {subject}")
                subprocess.run(['git', 'checkout', full_hash], 
                             cwd=CONFIG['build_dir'], check=True)
                subprocess.run(['make', 'build'], cwd=build_path, check=True)
                results = run_performance_test(short_hash)
                results['full_hash'] = full_hash
                append_to_report(report_path, short_hash, results, commit_desc=subject)
        
        print(f"\nResults written to: {report_path}")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
