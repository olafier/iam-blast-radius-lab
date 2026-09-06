"""
Fixed Action Set (100 actions) for the IAM Blast-Radius experiment.

Every identity (Policy A / B / C) is tested against this SAME set of 100 AWS
actions spanning 12 services. The only thing that changes between runs is the
identity's IAM permission scope.

Each action is a real AWS IAM action string, so the same list drives:
  - mock mode      : matched locally against the policy JSON (Allow only)
  - simulate mode  : sent to the real IAM Policy Simulator (real AWS decision,
                     no resources needed) -- see run_experiment.py

Weights (impact-weighted blast radius) are defined here, BEFORE the experiment,
so scores cannot be tuned to the results afterwards.

Category convention:
  READ     = observe state / read data (incl. reading secrets & decrypting)
  WRITE    = create or modify a resource / write data
  DESTROY  = delete a resource, disable auditing, or tear down infrastructure
  ESCALATE = change identity/permissions or assume another identity
"""

CATEGORY_WEIGHTS = {
    "READ": 1,
    "WRITE": 2,
    "DESTROY": 3,
    "ESCALATE": 4,
}

# (iam_action, category) grouped by service. Order is stable and defined up front.
_BY_SERVICE = {
    "S3": [
        ("s3:ListAllMyBuckets", "READ"),
        ("s3:ListBucket", "READ"),
        ("s3:GetObject", "READ"),
        ("s3:GetObjectVersion", "READ"),
        ("s3:GetBucketAcl", "READ"),
        ("s3:GetBucketPolicy", "READ"),
        ("s3:PutObject", "WRITE"),
        ("s3:CopyObject", "WRITE"),
        ("s3:CreateBucket", "WRITE"),
        ("s3:PutBucketAcl", "WRITE"),
        ("s3:PutBucketPolicy", "WRITE"),
        ("s3:DeleteObject", "DESTROY"),
        ("s3:DeleteBucket", "DESTROY"),
        ("s3:DeleteBucketPolicy", "DESTROY"),
    ],
    "EC2": [
        ("ec2:DescribeInstances", "READ"),
        ("ec2:DescribeSecurityGroups", "READ"),
        ("ec2:DescribeVolumes", "READ"),
        ("ec2:DescribeSnapshots", "READ"),
        ("ec2:DescribeVpcs", "READ"),
        ("ec2:CreateTags", "WRITE"),
        ("ec2:StartInstances", "WRITE"),
        ("ec2:RunInstances", "WRITE"),
        ("ec2:CreateSnapshot", "WRITE"),
        ("ec2:AuthorizeSecurityGroupIngress", "WRITE"),
        ("ec2:StopInstances", "DESTROY"),
        ("ec2:TerminateInstances", "DESTROY"),
        ("ec2:DeleteSnapshot", "DESTROY"),
        ("ec2:DeleteSecurityGroup", "DESTROY"),
    ],
    "IAM": [
        ("iam:ListUsers", "READ"),
        ("iam:ListRoles", "READ"),
        ("iam:ListPolicies", "READ"),
        ("iam:GetRole", "READ"),
        ("iam:GetPolicy", "READ"),
        ("iam:GetAccountAuthorizationDetails", "READ"),
        ("iam:CreateUser", "ESCALATE"),
        ("iam:CreateRole", "ESCALATE"),
        ("iam:CreateAccessKey", "ESCALATE"),
        ("iam:AttachUserPolicy", "ESCALATE"),
        ("iam:AttachRolePolicy", "ESCALATE"),
        ("iam:PutUserPolicy", "ESCALATE"),
        ("iam:PutRolePolicy", "ESCALATE"),
        ("iam:UpdateAssumeRolePolicy", "ESCALATE"),
        ("iam:CreatePolicyVersion", "ESCALATE"),
        ("iam:PassRole", "ESCALATE"),
        ("iam:DeleteUser", "DESTROY"),
        ("iam:DeleteRole", "DESTROY"),
    ],
    "STS": [
        ("sts:GetCallerIdentity", "READ"),
        ("sts:GetSessionToken", "READ"),
        ("sts:AssumeRole", "ESCALATE"),
    ],
    "Lambda": [
        ("lambda:ListFunctions", "READ"),
        ("lambda:GetFunction", "READ"),
        ("lambda:GetPolicy", "READ"),
        ("lambda:InvokeFunction", "WRITE"),
        ("lambda:CreateFunction", "WRITE"),
        ("lambda:UpdateFunctionCode", "WRITE"),
        ("lambda:UpdateFunctionConfiguration", "WRITE"),
        ("lambda:AddPermission", "ESCALATE"),
        ("lambda:CreateEventSourceMapping", "WRITE"),
        ("lambda:DeleteFunction", "DESTROY"),
    ],
    "DynamoDB": [
        ("dynamodb:ListTables", "READ"),
        ("dynamodb:DescribeTable", "READ"),
        ("dynamodb:GetItem", "READ"),
        ("dynamodb:Query", "READ"),
        ("dynamodb:PutItem", "WRITE"),
        ("dynamodb:UpdateItem", "WRITE"),
        ("dynamodb:DeleteItem", "DESTROY"),
        ("dynamodb:DeleteTable", "DESTROY"),
    ],
    "KMS": [
        ("kms:ListKeys", "READ"),
        ("kms:DescribeKey", "READ"),
        ("kms:GetKeyPolicy", "READ"),
        ("kms:Decrypt", "READ"),
        ("kms:Encrypt", "WRITE"),
        ("kms:PutKeyPolicy", "ESCALATE"),
        ("kms:ScheduleKeyDeletion", "DESTROY"),
    ],
    "CloudTrail": [
        ("cloudtrail:DescribeTrails", "READ"),
        ("cloudtrail:GetTrailStatus", "READ"),
        ("cloudtrail:LookupEvents", "READ"),
        ("cloudtrail:UpdateTrail", "WRITE"),
        ("cloudtrail:StopLogging", "DESTROY"),
        ("cloudtrail:DeleteTrail", "DESTROY"),
    ],
    "CloudWatch Logs": [
        ("logs:DescribeLogGroups", "READ"),
        ("logs:GetLogEvents", "READ"),
        ("logs:CreateLogGroup", "WRITE"),
        ("logs:PutLogEvents", "WRITE"),
        ("logs:DeleteLogGroup", "DESTROY"),
    ],
    "Secrets Manager": [
        ("secretsmanager:ListSecrets", "READ"),
        ("secretsmanager:DescribeSecret", "READ"),
        ("secretsmanager:GetSecretValue", "READ"),
        ("secretsmanager:CreateSecret", "WRITE"),
        ("secretsmanager:PutSecretValue", "WRITE"),
        ("secretsmanager:DeleteSecret", "DESTROY"),
    ],
    "SSM": [
        ("ssm:DescribeParameters", "READ"),
        ("ssm:GetParameter", "READ"),
        ("ssm:PutParameter", "WRITE"),
        ("ssm:DeleteParameter", "DESTROY"),
    ],
    "RDS": [
        ("rds:DescribeDBInstances", "READ"),
        ("rds:CreateDBSnapshot", "WRITE"),
        ("rds:ModifyDBInstance", "WRITE"),
        ("rds:StopDBInstance", "DESTROY"),
        ("rds:DeleteDBInstance", "DESTROY"),
    ],
}

# Human-readable names derived from the action string (e.g. "s3:GetObject" -> "Get object").
import re as _re


def _humanize(iam_action):
    op = iam_action.split(":", 1)[1]
    words = _re.sub(r"(?<!^)(?=[A-Z])", " ", op).split()
    return " ".join([words[0]] + [w.lower() for w in words[1:]]) if words else op


# Flattened, numbered action set.
ACTIONS = []
_n = 0
for _service, _items in _BY_SERVICE.items():
    for _iam_action, _category in _items:
        _n += 1
        ACTIONS.append({
            "n": _n,
            "name": _humanize(_iam_action),
            "category": _category,
            "iam_action": _iam_action,
            "service": _service,
        })

assert len(ACTIONS) == 100, f"expected 100 actions, got {len(ACTIONS)}"


def weight_of(action):
    """Return the impact weight for an action dict."""
    return CATEGORY_WEIGHTS[action["category"]]


if __name__ == "__main__":
    from collections import Counter
    c = Counter(a["category"] for a in ACTIONS)
    print(f"{len(ACTIONS)} actions across {len(_BY_SERVICE)} services")
    for cat in CATEGORY_WEIGHTS:
        print(f"  {cat:9s} {c[cat]:3d}  (weight {CATEGORY_WEIGHTS[cat]})")
    print("  total weight:", sum(weight_of(a) for a in ACTIONS))
