import json, base64, subprocess

# Read the session JSON provided by user
# accessToken and sessionToken from chatgpt.com/api/auth/session
access_token = "eyJhbGciOiJSUzI1NiIsImtpZCI6ImFlNjc5NWRjLTRiYWUtNDE4YS04NjVkLTA4YTY0MzllZWRhNiIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiaHR0cHM6Ly9hcGkub3BlbmFpLmNvbS92MSJdLCJjbGllbnRfaWQiOiJhcHBfWDh6WTZ2VzJwUTl0UjNkRTduSzFqTDVnSCIsImh0dHBzOi8vYXBpLm9wZW5haS5jb20vYXV0aCI6eyJjaGF0Z3B0X2FjY291bnRfaWQiOiIxMzA5YTFkMS1iNzVlLTQ1YWEtYTcyMi1jZGY3YzU3YTJmMDYiLCJjaGF0Z3B0X2FjY291bnRfdXNlcl9pZCI6InVzZXItSjJ4bnE1aUtBVUV1am5nZkcxa3VRa0ZQX18xMzA5YTFkMS1iNzVlLTQ1YWEtYTcyMi1jZGY3YzU3YTJmMDYiLCJjaGF0Z3B0X2NvbXB1dGVfcmVzaWRlbmN5Ijoibm9fY29uc3RyYWludCIsImNoYXRncHRfcGxhbl90eXBlIjoiZWR1IiwiY2hhdGdwdF91c2VyX2lkIjoidXNlci1KMnhucTVpS0FVRXVqbmdmRzFrdVFrRlAiLCJzc29fY29ubmVjdGlvbl9pZCI6ImNvbm5fMDFKUDVWWEFWRFg2RUtSUFJWVzlXMEpNNjYiLCJ1c2VyX2lkIjoidXNlci1KMnhucTVpS0FVRXVqbmdmRzFrdVFrRlAiLCJ2ZXJpZmllZF9vcmdfaWRzIjpbIm9yZy1TTDVjc3VtTWh5b0tTekFCSFIzSUNNQWYiLCJvcmctTGFBQ1hrNkNFM0Fqb2tmNWxXdWF1cnZhIl0sInZlcmlmaWVkX3dzX2lkcyI6WyIxMzA5YTFkMS1iNzVlLTQ1YWEtYTcyMi1jZGY3YzU3YTJmMDYiXX0sImh0dHBzOi8vYXBpLm9wZW5haS5jb20vcHJvZmlsZSI6eyJlbWFpbCI6ImtldmluLmhlcm5hbmRlei42MTRAbXkuY3N1bi5lZHUiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZX0sImlzcyI6Imh0dHBzOi8vYXV0aC5vcGVuYWkuY29tIiwicHdkX2F1dGhfdGltZSI6MTc4MzQxNDkxMDkwOCwic2NwIjpbIm9wZW5pZCIsImVtYWlsIiwicHJvZmlsZSIsIm9mZmxpbmVfYWNjZXNzIiwibW9kZWwucmVxdWVzdCIsIm1vZGVsLnJlYWQiLCJvcmdhbml6YXRpb24ucmVhZCIsIm9yZ2FuaXphdGlvbi53cml0ZSJdLCJzZXNzaW9uX2lkIjoiYXV0aHNlc3NfN2c2VHBLWFpsb3d1ZkgyeDg4TlBxTGdxIiwic2wiOnRydWUsInN1YiI6InNhbWxwfHByb2ZfMDFLMEJIRllKUjJROU5KSzZEWkNFWFBKNjd8a2V2aW4uaGVybmFuZGV6LjYxNEBteS5jc3VuLmVkdSIsImlhdCI6MTc4MzQxNDkxMywiZXhwIjoxNzg0Mjc4OTEzLCJqdGkiOiI4NjlkMWZkNWE3N2M0NjkxOWY2Mzg1MmE1YjI4NDk2ZiIsIm5iZiI6MTc4MzQxNDkxM30.T0VULNMJVXRYbaiABNFNRvEQT05iP5-S1EYp8x3qiI3VpMIVpi5eIoAMqevj9I5vC1XYQlEPYLYzf48KQ6y68dGOISqb3NkefoboIWEVgJSdnZgD3DVP10M_9bafTx_nu0Q6LXCb_F2AaNLNV8QF9U5ocAVO1Aun9qCFP6rNNSfdHZp0zpw1fQz-vczc1-aZJKmWDsfUS0VwU7DLCdb3tnMigZvK0VRy-WMmgF47tuQS7DXAUgZVRQPJgpuGG6DsEuvI4YERUFRxEZ7nBeiX6_bSBp3htTPkeole6-duqPs0Y_jWF6gnwdNE5PDB4LdBN0P20xb3yk-lgpb8TnS6hH4UfMEQDxW7YqjaaMYfTqUU532WUOXfH7SmOAQq4LELRHKsUfrjpg85K-0jL0MZ4SxpgG1PzYayrhcai-rIcmghlhDGBdOeYFrKINbY8jeZgCZDETHEsgU1I-mE1_km4ysi_YFp2f9iIXLecDvUCJDwTcWCtgoi2HQWb406VvZLCSKpDt_eRptDooiMrg5IyV_kbvvF4giXZgQwfgOhuY99MQ-48yPLhMprelMsbd7HavxwBU9F4TIPD_MTZ2hOY9UcTaLDVWNRsTEgbFWU9Bkl9OXoJvpwECKUJViAqmnyeiC6OCfKWrn_ziVsylOEt_Eqqnmcer3DAL0ajqByvOI"

auth = {
    "access_token": access_token,
    "id_token": access_token,
    "refresh_token": "",
    "session_token": "",
    "account_id": "1309a1d1-b75e-45aa-a722-cdf7c57a2f06",
    "last_refresh": "",
    "expired": "2026-10-11T07:28:51.854Z",
    "disabled": False,
    "type": "codex"
}

# Write JSON
path = r'D:\Work\赛狐\Cursor\us_openai_api_proxy\tools\csun_auth.json'
with open(path, 'w') as f:
    json.dump(auth, f, indent=2)
print(f"Written: {path}")

# SCP to US Ubuntu
result = subprocess.run([
    'scp', '-o', 'ConnectTimeout=10',
    path,
    'us-ubuntu-proxy:/tmp/csun_auth.json'
], capture_output=True, text=True)
print(f"SCP: {result.returncode} {result.stderr}")

# Move to auth dir on server
result = subprocess.run([
    'ssh', '-o', 'ConnectTimeout=10', 'us-ubuntu-proxy',
    'cp /tmp/csun_auth.json /opt/cliproxyapi/auth/codex-kevin.hernandez.614@my.csun.edu-edu.json && '
    'chmod 600 /opt/cliproxyapi/auth/codex-kevin.hernandez.614@my.csun.edu-edu.json && '
    'echo "File created" && '
    'ls -la /opt/cliproxyapi/auth/'
], capture_output=True, text=True)
print(f"SSH: {result.returncode}")
print(result.stdout)
print(result.stderr)
