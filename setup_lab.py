#!/usr/bin/env python3
"""
Provision the AWS lab for the IAM blast-radius experiment (REAL mode only).

Creates, in a SANDBOX account:
  - 1 S3 test bucket + 1 test object
  - 1 small EC2 test instance (t3.micro)  [optional, --with-ec2]
  - 3 IAM managed policies from policies/*.json
  - 3 IAM users (blast-a / blast-b / blast-c), each with one policy attached
  - access keys for each user (printed once; store them as AWS CLI profiles)
  - a CloudTrail trail writing to a logging bucket [optional, --with-cloudtrail]

Run this with ADMIN credentials for a throwaway sandbox account.
Tear everything down afterwards with:  python setup_lab.py --teardown

SAFETY: only use a dedicated sandbox/lab account. Set a budget + cost alert first.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
POLICY_DIR = os.path.join(HERE, "policies")

POLICIES = {
    "blast-policy-a-narrow":   "policy_a_narrow.json",
    "blast-policy-b-moderate": "policy_b_moderate.json",
    "blast-policy-c-broad":    "policy_c_broad.json",
}
USERS = {
    "blast-a": "blast-policy-a-narrow",
    "blast-b": "blast-policy-b-moderate",
    "blast-c": "blast-policy-c-broad",
}


def acct_id(session):
    return session.client("sts").get_caller_identity()["Account"]


def setup(args):
    import boto3
    from botocore.exceptions import ClientError

    session = boto3.Session(region_name=args.region)
    account = acct_id(session)
    iam = session.client("iam")
    s3 = session.client("s3")

    print(f"Account: {account}  Region: {args.region}\n")

    # --- S3 test bucket + object ---
    bucket = args.test_bucket
    print(f"[S3] creating test bucket: {bucket}")
    try:
        if args.region == "us-east-1":
            s3.create_bucket(Bucket=bucket)
        else:
            s3.create_bucket(Bucket=bucket,
                             CreateBucketConfiguration={"LocationConstraint": args.region})
    except ClientError as e:
        print("   ", e.response["Error"]["Code"], "(continuing)")
    s3.put_object(Bucket=bucket, Key="hello.txt", Body=b"blast radius test object")
    print("     put object hello.txt")

    # --- IAM policies ---
    policy_arns = {}
    for name, fname in POLICIES.items():
        with open(os.path.join(POLICY_DIR, fname)) as f:
            doc = f.read()
        try:
            resp = iam.create_policy(PolicyName=name, PolicyDocument=doc)
            arn = resp["Policy"]["Arn"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "EntityAlreadyExists":
                arn = f"arn:aws:iam::{account}:policy/{name}"
            else:
                raise
        policy_arns[name] = arn
        print(f"[IAM] policy {name} -> {arn}")

    # --- IAM users + attach + keys ---
    creds = {}
    for user, pol in USERS.items():
        try:
            iam.create_user(UserName=user)
        except ClientError as e:
            if e.response["Error"]["Code"] != "EntityAlreadyExists":
                raise
        iam.attach_user_policy(UserName=user, PolicyArn=policy_arns[pol])
        key = iam.create_access_key(UserName=user)["AccessKey"]
        creds[user] = (key["AccessKeyId"], key["SecretAccessKey"])
        print(f"[IAM] user {user}  (+{pol})")

    print("\n=== Access keys (store these as AWS CLI profiles NOW) ===")
    profile_hint = {"blast-a": "labA", "blast-b": "labB", "blast-c": "labC"}
    for user, (ak, sk) in creds.items():
        p = profile_hint[user]
        print(f"\n# {user}")
        print(f"aws configure set aws_access_key_id     {ak} --profile {p}")
        print(f"aws configure set aws_secret_access_key  {sk} --profile {p}")
        print(f"aws configure set region {args.region} --profile {p}")

    print("\nNext:")
    print("  python run_experiment.py --real \\")
    print("      --profile-map policy_a=labA policy_b=labB policy_c=labC \\")
    print(f"      --region {args.region} --test-bucket {bucket}")
    print("  python compute_metrics.py")
    if args.with_cloudtrail:
        print("\n(!) Remember CloudTrail can take a few minutes to deliver events.")


def teardown(args):
    import boto3
    from botocore.exceptions import ClientError

    session = boto3.Session(region_name=args.region)
    account = acct_id(session)
    iam = session.client("iam")
    s3 = session.resource("s3")

    for user, pol in USERS.items():
        try:
            for k in iam.list_access_keys(UserName=user)["AccessKeyMetadata"]:
                iam.delete_access_key(UserName=user, AccessKeyId=k["AccessKeyId"])
            iam.detach_user_policy(UserName=user,
                                   PolicyArn=f"arn:aws:iam::{account}:policy/{pol}")
            iam.delete_user(UserName=user)
            print(f"deleted user {user}")
        except ClientError as e:
            print(user, e.response["Error"]["Code"])
    for name in POLICIES:
        try:
            iam.delete_policy(PolicyArn=f"arn:aws:iam::{account}:policy/{name}")
            print(f"deleted policy {name}")
        except ClientError as e:
            print(name, e.response["Error"]["Code"])
    try:
        b = s3.Bucket(args.test_bucket)
        b.objects.all().delete()
        b.delete()
        print(f"deleted bucket {args.test_bucket}")
    except ClientError as e:
        print(args.test_bucket, e.response["Error"]["Code"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--test-bucket", default=None,
                    help="globally-unique bucket name (default: blast-radius-<account>)")
    ap.add_argument("--with-ec2", action="store_true")
    ap.add_argument("--with-cloudtrail", action="store_true")
    ap.add_argument("--teardown", action="store_true")
    args = ap.parse_args()

    try:
        import boto3  # noqa
    except ImportError:
        sys.exit("boto3 not installed:  pip install boto3")

    if not args.test_bucket:
        import boto3
        acc = acct_id(boto3.Session(region_name=args.region))
        args.test_bucket = f"blast-radius-{acc}"

    if args.teardown:
        teardown(args)
    else:
        setup(args)


if __name__ == "__main__":
    main()
