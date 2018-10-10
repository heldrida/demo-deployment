from awacs.aws import Action, Allow, Policy, Principal, Statement
from troposphere import (
    Template, route53, cloudformation, ec2, ecs, elasticloadbalancingv2, iam,
    logs, sqs,
    Equals, GetAtt, If, ImportValue, Join, Not, Parameter, Ref, Sub, FindInMap
)
from cfn_encrypt import GetSsmValue
from uuid import uuid4
import cfn_datadog
from cfn_flip import to_yaml

t = Template()

t.add_description("ECS Service template")


def update_dummy_wch(template):
    template.add_resource(cloudformation.WaitConditionHandle(
        str(uuid4()).replace("-", "")
    ))


update_dummy_wch(t)

# PARAMETERS

# Defined in config file

alb_stack = t.add_parameter(Parameter(
    "AlbStack",
    AllowedPattern="^.+$",
    Type="String",
    Description="ALB stack name",
    Default="NONE"
))

ecs_stack = t.add_parameter(Parameter(
    "EcsStack",
    AllowedPattern="^.+$",
    Type="String",
    Description="ECS stack name",
    Default="NONE"
))

encrypt_lambda_stack = t.add_parameter(Parameter(
    "EncryptLambdaStack",
    AllowedPattern="^.+$",
    Type="String",
    Description="Encrypt Lambda stack name",
    Default="cfn-encrypt"
))

datadog_stack = t.add_parameter(Parameter(
    "DatadogStack",
    Type="String",
    Description="Datadog stack name",
    Default="cfn-datadog"
))

network_stack = t.add_parameter(Parameter(
    "NetworkStack",
    AllowedPattern="^.+$",
    Type="String",
    Description="Network stack name",
    Default="NONE"
))

container_name = t.add_parameter(Parameter(
    "ContainerName",
    AllowedPattern="^.+$",
    Type="String",
    Default="simple-app",
    Description="Container name from the task-definition template",
))

container_port = t.add_parameter(Parameter(
    "ContainerPort",
    Type="Number",
    Description="Container port",
    Default=80
))

listener_priority = t.add_parameter(Parameter(
    "ListenerPriority",
    Description="Listener Rule Priority, must be unique across listeners",
    Type="Number",
    Default=10
))

service_path = t.add_parameter(Parameter(
    "ServicePath",
    AllowedPattern="^.+$",
    Type="String",
    Description="Optional: Path portion of the service URL (use ServicePath OR ServiceHost, NONE for none)",
    Default="NONE"
))

service_path_condition = "ServicePathCondition"
t.add_condition(service_path_condition,
                Not(Equals(Ref(service_path), service_path.Default)))

service_host = t.add_parameter(Parameter(
    "ServiceHost",
    AllowedPattern="^.+$",
    Type="String",
    Description="Optional: Hostname for the ALB listener rule (use ServicePath OR ServiceHost, NONE for none)",
    Default="NONE"
))

service_host_condition = "ServiceHostCondition"
t.add_condition(service_host_condition,
                Not(Equals(Ref(service_host), service_host.Default)))

autoscaling_max = t.add_parameter(Parameter(
    "AutoscalingMax",
    Type="Number",
    Description="Maximum number of tasks to autoscale",
    Default=3
))

autoscaling_min = t.add_parameter(Parameter(
    "AutoscalingMin",
    Type="Number",
    Description="Minimum number of tasks to autoscale",
    Default=3
))

health_check_path = t.add_parameter(Parameter(
    "HealthCheckPath",
    AllowedPattern="^.+$",
    Type="String",
    Description="Healthcheck path",
    Default="NONE"
))

# Defined by pipeline (Parameters override)

certificate_arn = t.add_parameter(Parameter(
    "CertificateArn",
    AllowedPattern="^.+$",
    Type="String",
    Description="Optional: When certificate ARN is provided, rules are created on ALB listener 443 (NONE for none)",
    Default="NONE"
))

certificate_arn_condition = "CertificateArnCondition"
t.add_condition(certificate_arn_condition,
                Not(Equals(Ref(certificate_arn), certificate_arn.Default)))

task_definition = t.add_parameter(Parameter(
    "TaskDefinition",
    Type="String",
    Default="arn:aws:ecs:eu-west-1:145601632047:task-definition/demo:4",
    Description="The ARN of the task definition (including the revision number) that you want to run on the cluster, such as arn:aws:ecs:us-east-1:123456789012:task-definition/mytask:3. You can't use :latest to specify a revision because it's ambiguous. For example, if AWS CloudFormation needed to roll back an update, it wouldn't know which revision to roll back to. ",
))

stack_env = t.add_parameter(Parameter(
    "StackEnv",
    AllowedPattern="^.+$",
    Type="String",
    AllowedValues=["PROD", "UAT", "OTHER"],
    Description="When PROD is selected Datadog will be installed on the instances. Use UAT for UAT stacks and OTHER for everything else",
    Default="OTHER"
))

is_prod = "IsProd"
t.add_condition(is_prod, Equals(Ref(stack_env), "PROD"))

# kms_key_arn = ImportValue(Sub("${EncryptLambdaStack}-KmsKeyArn"))
# get_ssm_value_lambda_arn = ImportValue(Sub("${EncryptLambdaStack}-GetSsmValueLambdaArn"))

# Get RDS password from SSM
# database_password = t.add_resource(GetSsmValue(
#     "DatabasePassword",
#     ServiceToken=get_ssm_value_lambda_arn,
#     Name=Join("/", ["", Ref(rds_stack), "DbMasterPassword"]),
#     KeyId=kms_key_arn
# ))

# METADATA

t.add_metadata({
    'AWS::CloudFormation::Interface': {
        'ParameterGroups': [
            {
                'Label': {
                    'default': 'ECS Service',
                },
                'Parameters': [
                    health_check_path.title,
                    autoscaling_max.title,
                    autoscaling_min.title,
                ]
            },
            {
                'Label': {
                    'default': 'ALB Listener Rule',
                },
                'Parameters': [
                    service_path.title,
                    service_host.title,
                    listener_priority.title,
                ]
            },
            {
                'Label': {
                    'default': 'Container',
                },
                'Parameters': [
                    container_name.title,
                    container_port.title,
                ]
            },
            {
                'Label': {
                    'default': 'Dependent stacks',
                },
                'Parameters': [
                    alb_stack.title,
                    ecs_stack.title,
                    encrypt_lambda_stack.title,
                    datadog_stack.title,
                    network_stack.title,
                ]
            },
            {
                'Label': {
                    'default': 'Parameters override (pipeline-ecs-service-api stack)',
                },
                'Parameters': [
                    certificate_arn.title,
                    stack_env.title,
                    task_definition.title
                ]
            },
        ]
    }
})

# RESOURCES

"""
Log group
"""

log_group = t.add_resource(logs.LogGroup(
    "LogGroup",
    LogGroupName=Ref("AWS::StackName"),
    RetentionInDays=60
))

# ROLES

task_role = t.add_resource(iam.Role(
    "TaskRole",
    AssumeRolePolicyDocument=Policy(
        Version="2012-10-17",
        Statement=[
            Statement(
                Effect=Allow,
                Principal=Principal("Service", "ecs-tasks.amazonaws.com"),
                Action=[
                    Action("sts", "AssumeRole"),
                ]
            )
        ]
    ),
    Path="/",
    Policies=[
        iam.Policy(
            PolicyName=Join("-", [Ref("AWS::StackName"), "task-policy"]),
            PolicyDocument=Policy(
                Version="2012-10-17",
                Statement=[
                    Statement(
                        Effect=Allow,
                        Action=[
                            Action("logs", "CreateLogStream"),
                            Action("logs", "PutLogEvents"),
                            Action("logs", "CreateLogGroup"),
                        ],
                        Resource=[
                            Join(":", ["arn:aws:logs", Ref("AWS::Region"),
                                       Ref("AWS::AccountId"), "log-group",
                                       Ref(log_group), "*"]),
                        ]
                    ),
                    Statement(
                        Effect=Allow,
                        Action=[
                            Action("ssm", "DescribeParameters"),
                            Action("ssm", "GetParameters"),
                            Action("ssm", "GetParametersByPath"),
                            Action("ssm", "GetParameter"),
                        ],
                        Resource=[
                            Join(":", ["arn:aws:ssm", Ref("AWS::Region"),
                                       Ref("AWS::AccountId"), "*"]),
                        ]
                    ),
                    Statement(
                        Effect=Allow,
                        Action=[
                            Action("kms", "Decrypt"),
                        ],
                        Resource=[
                            ImportValue(
                                Sub("${EncryptLambdaStack}-KmsKeyArn")),
                        ]
                    ),
                ]
            )
        )
    ]
))

# Attach a policy with attach_ssm_policy that allows listing and reading of parameters from ParameterStore
# If we have any encrypted variables, attach a policy to allow using the KMS Key exported by EncryptLambdaStack
# PR's welcome

service_role = t.add_resource(iam.Role(
    "ServiceRole",
    AssumeRolePolicyDocument=Policy(
        Version="2012-10-17",
        Statement=[
            Statement(
                Effect=Allow,
                Principal=Principal("Service", "ecs.amazonaws.com"),
                Action=[
                    Action("sts", "AssumeRole"),
                ]
            )
        ]
    ),
    Path="/",
    Policies=[
        iam.Policy(
            PolicyName=Join("-", [Ref("AWS::StackName"), "service-policy"]),
            PolicyDocument=Policy(
                Version="2012-10-17",
                Statement=[
                    Statement(
                        Effect=Allow,
                        Action=[
                            Action("ec2", "AuthorizeSecurityGroupIngress"),
                            Action("ec2", "Describe*"),
                            Action("elasticloadbalancing",
                                   "DeregisterInstancesFromLoadBalancer"),
                            Action("elasticloadbalancing",
                                   "DeregisterTargets"),
                            Action("elasticloadbalancing", "Describe*"),
                            Action("elasticloadbalancing",
                                   "RegisterInstancesWithLoadBalancer"),
                            Action("elasticloadbalancing", "RegisterTargets"),
                        ],
                        Resource=[
                            "*"
                        ]
                    ),
                    Statement(
                        Effect=Allow,
                        Action=[
                            Action("logs", "CreateLogStream"),
                            Action("logs", "PutLogEvents"),
                            Action("logs", "CreateLogGroup"),
                        ],
                        Resource=[
                            Join(":", ["arn:aws:logs", Ref("AWS::Region"),
                                       Ref("AWS::AccountId"), "log-group",
                                       Ref(log_group), "*"]),
                        ]
                    ),
                ]
            )
        )
    ]
))

autoscale_role = t.add_resource(iam.Role(
    "AutoscaleRole",
    AssumeRolePolicyDocument=Policy(
        Version="2012-10-17",
        Statement=[
            Statement(
                Effect=Allow,
                Principal=Principal("Service",
                                    "application-autoscaling.amazonaws.com"),
                Action=[
                    Action("sts", "AssumeRole"),
                ]
            )
        ]
    ),
    Path="/",
    Policies=[
        iam.Policy(
            PolicyName=Join("-", [Ref("AWS::StackName"), "autoscale-policy"]),
            PolicyDocument=Policy(
                Version="2012-10-17",
                Statement=[
                    Statement(
                        Effect=Allow,
                        Action=[
                            Action("ecs", "DescribeServices"),
                            Action("ecs", "UpdateService"),
                        ],
                        Resource=[
                            "*"
                        ]
                    ),
                    Statement(
                        Effect=Allow,
                        Action=[
                            Action("cloudwatch", "DescribeAlarms"),
                        ],
                        Resource=[
                            "*"
                        ]
                    )
                ],
            )
        )
    ]
))

# RESOURCES

"""
Create a TargetGroup to be attached to ALB of the ECS-stack
"""
target_group = t.add_resource(elasticloadbalancingv2.TargetGroup(
    "TargetGroup",
    Name=Join("-", [Ref(stack_env), "Tg", Ref(container_name)]),
    Port=Ref(container_port),
    Protocol="HTTP",
    HealthCheckPath=Ref(health_check_path),
    HealthCheckIntervalSeconds="30",
    HealthCheckProtocol="HTTP",
    HealthCheckTimeoutSeconds="10",
    HealthyThresholdCount="4",
    Matcher=elasticloadbalancingv2.Matcher(HttpCode="200,302"),
    UnhealthyThresholdCount="3",
    VpcId=ImportValue(Sub("${NetworkStack}-Vpc")),
    TargetGroupAttributes=[
        elasticloadbalancingv2.TargetGroupAttribute(
            Key="deregistration_delay.timeout_seconds",
            Value="30",
        ),
    ],
    Tags=[{
        "Key": "TargetGroupName",
        "Value": Join("-", ["Tg", Ref(container_name)])
    }]
))

"""
Add the TargetGroup to a Listener on the ALB
 - path-pattern and host-header are given as Parameters to this stack
"""
listener_rule1 = t.add_resource(elasticloadbalancingv2.ListenerRule(
    "ListenerRule1",
    Actions=[
        elasticloadbalancingv2.Action(
            TargetGroupArn=Ref(target_group),
            Type="forward"
        )
    ],
    Conditions=[
        If(service_path_condition,
           elasticloadbalancingv2.Condition(
               Field="path-pattern",
               Values=[
                   Ref(service_path),
               ]
           ),
           Ref("AWS::NoValue")
           ),
        If(service_host_condition,
           elasticloadbalancingv2.Condition(
               Field="host-header",
               Values=[
                   If(is_prod,
                      Ref(service_host),
                      Join(".", ["uat", Ref(service_host)]),
                      ),
               ]
           ),
           Ref("AWS::NoValue")
           ),
    ],
    ListenerArn=ImportValue(Sub("${AlbStack}-AlbPublicListener80")),
    Priority=Ref(listener_priority)
))

listener_rule2 = t.add_resource(elasticloadbalancingv2.ListenerRule(
    "ListenerRule2",
    Condition=certificate_arn_condition,
    Actions=[
        elasticloadbalancingv2.Action(
            TargetGroupArn=Ref(target_group),
            Type="forward"
        )
    ],
    Conditions=[
        If(service_path_condition,
           elasticloadbalancingv2.Condition(
               Field="path-pattern",
               Values=[
                   Ref(service_path),
               ]
           ),
           Ref("AWS::NoValue")
           ),
        If(service_host_condition,
           elasticloadbalancingv2.Condition(
               Field="host-header",
               Values=[
                   If(is_prod,
                      Ref(service_host),
                      Join(".", ["uat", Ref(service_host)]),
                      ),
               ]
           ),
           Ref("AWS::NoValue")
           ),
    ],
    ListenerArn=ImportValue(Sub("${AlbStack}-AlbPublicListener443")),
    Priority=Ref(listener_priority)
))

# Allow NAT instances to access Public ALB
sg_alb_public_ingress_rules = {}
sg_alb_public_ingress_rules443 = {}
for az in ["A", "B", "C"]:
    sg_alb_public_ingress_rules[az] = t.add_resource(
        ec2.SecurityGroupIngress(
            "EcsServiceApiWebIngressRule" + az,
            CidrIp=Join("/",
                        [ImportValue(Sub("${NetworkStack}-NatIpPublic" + az)),
                         "32"]),
            IpProtocol="6",
            FromPort=80,
            ToPort=80,
            GroupId=ImportValue(Sub("${AlbStack}-SgAlbPublicGroupId"))
        ),
    )
    sg_alb_public_ingress_rules443[az] = t.add_resource(
        ec2.SecurityGroupIngress(
            "EcsServiceApiWebIngressRuleSsl" + az,
            Condition=certificate_arn_condition,
            CidrIp=Join("/",
                        [ImportValue(Sub("${NetworkStack}-NatIpPublic" + az)),
                         "32"]),
            IpProtocol="6",
            FromPort=443,
            ToPort=443,
            GroupId=ImportValue(Sub("${AlbStack}-SgAlbPublicGroupId"))
        )
    )

"""
Service definition
 - Spread to several AZs for HA
 - Binpack to minimize number of required hosts per AZ
"""
service = t.add_resource(ecs.Service(
    "Service",
    Cluster=ImportValue(Sub("${EcsStack}-Cluster")),
    DependsOn=service_role,
    DesiredCount=Ref(autoscaling_min),
    LoadBalancers=[
        ecs.LoadBalancer(
            ContainerName=Ref(container_name),
            ContainerPort=Ref(container_port),
            TargetGroupArn=Ref(target_group)
        ),
    ],
    PlacementStrategies=[
        ecs.PlacementStrategy(
            Type="spread",
            Field="attribute:ecs.availability-zone"
        )
    ],
    Role=Ref(service_role),
    TaskDefinition=Ref(task_definition),
    DeploymentConfiguration=ecs.DeploymentConfiguration(
        MaximumPercent="200",
        MinimumHealthyPercent="50"
    ),
))

# """
# Route53 HostedZone records
#  - HostedZone must already exist!
# """
#
# public_route53_record_set = t.add_resource(
#     route53.RecordSetType(
#         'PublicRoute53RecordSet',
#         HostedZoneName="aws.nh-at5.nl.",
#         Comment='Alias Record for ${AWS::StackName}',
#         Name=If(is_prod,
#                 "api.aws.nh-at5.nl",
#                 "uat.api.aws.nh-at5.nl",
#                 ),
#         Type='A',
#         AliasTarget=route53.AliasTarget(
#             hostedzoneid=FindInMap(hosted_zones, Ref("AWS::Region"), "elb"),
#             dnsname=ImportValue(Sub("${AlbStack}-AlbPublicDNSName")),
#         ),
#     )
# )

"""
Datadog monitors
 - Number of running services is 0 during the last 1 hour.
"""

t.add_resource(cfn_datadog.MetricAlert(
    "DatadogEcsServiceApiRunningServicesCountAlert",
    Condition=is_prod,
    ServiceToken=ImportValue(Sub("${DatadogStack}-LambdaArn")),
    name="ECS Service API Running Services Count ( CFN )",
    query=Join("", ["min(last_1h):avg:aws.ecs.service.running{service:",
                    GetAtt(service, "Name"), "} <= 0"]),
    message="ECS Service API - Number of running services is below or equal to 0 @pagerduty-NHMediaDatadog",
    options=cfn_datadog.MetricAlertOptions(
        timeout_h=0,
        notify_no_data=True,
        no_data_timeframe=10,
        notify_audit=False,
        new_host_delay=300,
        include_tags=False,
        escalation_message="",
        locked=False,
        renotify_interval="0",
        evaluation_delay="900",
        thresholds=cfn_datadog.Thresholds(
            critical=0,
        )
    )
))

"""
Make the service a ScalableTarget
"""
# scalable_target = t.add_resource(applicationautoscaling.ScalableTarget(
#     'ScalableTarget',
#     MaxCapacity=Ref(autoscaling_max),
#     MinCapacity=Ref(autoscaling_min),
#     ResourceId=Join("/", [
#         "service",
#         ImportValue(Sub("${EcsStack}-Cluster")),
#         GetAtt(service, "Name")
#     ]),
#     RoleARN=GetAtt(autoscale_role, "Arn"),
#     ScalableDimension='ecs:service:DesiredCount',
#     ServiceNamespace='ecs',
# ))
#
# """
# Scale out/in policies
#  - Scale out +50%, scale in -1
# """
# service_scale_out_policy = t.add_resource(applicationautoscaling.ScalingPolicy(
#     'ServiceScaleOutPolicy',
#     PolicyName='ServiceScaleOutPolicy',
#     PolicyType='StepScaling',
#     ScalingTargetId=Ref(scalable_target),
#     StepScalingPolicyConfiguration=applicationautoscaling.StepScalingPolicyConfiguration(
#         AdjustmentType='PercentChangeInCapacity',
#         Cooldown=300,
#         MetricAggregationType='Average',
#         StepAdjustments=[
#             applicationautoscaling.StepAdjustment(
#                 MetricIntervalLowerBound=0,
#                 ScalingAdjustment=50,
#             ),
#         ],
#     ),
# ))
#
# service_scale_in_policy = t.add_resource(applicationautoscaling.ScalingPolicy(
#     'ServiceScaleInPolicy',
#     PolicyName='ServiceScaleInPolicy',
#     PolicyType='StepScaling',
#     ScalingTargetId=Ref(scalable_target),
#     StepScalingPolicyConfiguration=applicationautoscaling.StepScalingPolicyConfiguration(
#         AdjustmentType='ChangeInCapacity',
#         Cooldown=300,
#         MetricAggregationType='Average',
#         StepAdjustments=[
#             applicationautoscaling.StepAdjustment(
#                 MetricIntervalUpperBound=0,
#                 ScalingAdjustment=-1,
#             ),
#         ],
#     ),
# ))
#
# service_cpu_alarm_high = t.add_resource(cloudwatch.Alarm(
#     'ServiceCpuAlarmHigh',
#     AlarmDescription='Scale out if avg CPU usage of a service is >70% for 2 minutes',
#     Namespace='AWS/ECS',
#     Dimensions=[cloudwatch.MetricDimension(
#         Name="ServiceName",
#         Value=GetAtt(service, "Name")
#     ),
#         cloudwatch.MetricDimension(
#             Name="ClusterName",
#             Value=ImportValue(Sub("${EcsStack}-Cluster"))
#         )],
#     MetricName='CPUUtilization',
#     Statistic='Average',
#     Period='60',
#     EvaluationPeriods='2',
#     Threshold='70',
#     ComparisonOperator='GreaterThanThreshold',
#     AlarmActions=[Ref(service_scale_out_policy)],
# ))
#
# service_cpu_alarm_low = t.add_resource(cloudwatch.Alarm(
#     'ServiceCpuAlarmLow',
#     AlarmDescription='Scale in if avg CPU usage of a service is <25% for 20 minutes',
#     Namespace='AWS/ECS',
#     Dimensions=[cloudwatch.MetricDimension(
#         Name="ServiceName",
#         Value=GetAtt(service, "Name")
#     ),
#         cloudwatch.MetricDimension(
#             Name="ClusterName",
#             Value=ImportValue(Sub("${EcsStack}-Cluster"))
#         )],
#     MetricName='CPUUtilization',
#     Statistic='Average',
#     Period='60',
#     EvaluationPeriods='20',
#     Threshold='25',
#     ComparisonOperator='LessThanThreshold',
#     AlarmActions=[Ref(service_scale_in_policy)],
# ))

print(to_yaml(t.to_json()))
