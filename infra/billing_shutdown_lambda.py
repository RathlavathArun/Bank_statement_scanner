"""
Lambda function triggered by a CloudWatch billing alarm via SNS.
Scales all ECS services in the bank-statement cluster down to 0 tasks.
"""
import boto3
import json
import os

def handler(event, context):
    region = os.environ.get("TARGET_REGION", "ap-south-1")
    cluster = os.environ.get("ECS_CLUSTER", "bank-statement-cluster")

    ecs = boto3.client("ecs", region_name=region)

    # List all services in the cluster
    paginator = ecs.get_paginator("list_services")
    service_arns = []
    for page in paginator.paginate(cluster=cluster):
        service_arns.extend(page["serviceArns"])

    if not service_arns:
        print(f"No services found in cluster {cluster}")
        return {"status": "no_services"}

    # Scale each service down to 0
    stopped = []
    for arn in service_arns:
        service_name = arn.split("/")[-1]
        try:
            ecs.update_service(
                cluster=cluster,
                service=service_name,
                desiredCount=0,
            )
            stopped.append(service_name)
            print(f"Scaled down {service_name} to 0")
        except Exception as e:
            print(f"Failed to scale down {service_name}: {e}")

    print(f"Billing alarm triggered — stopped {len(stopped)} services: {stopped}")
    return {"status": "shutdown_complete", "stopped_services": stopped}
