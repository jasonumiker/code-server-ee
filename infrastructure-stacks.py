from aws_cdk import (
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    core
)

class CodeServerStack(core.Stack):

    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        code_server_vpc = ec2.Vpc(
            self, "VPC",
            cidr="10.0.0.0/16"
        )

        # Create IAM Role For code-build
        code_server_role = iam.Role(
            self, "CodeServerRole",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("ec2.amazonaws.com")
            ),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
            ]
        )

        # Create EC2 Instance Profile for that Role
        instance_profile = iam.CfnInstanceProfile(
            self, "InstanceProfile",
            roles=[code_server_role.role_name]            
        )

        # Latest Amazon Linux AMI
        amzn_linux = ec2.MachineImage.latest_amazon_linux(
            generation=ec2.AmazonLinuxGeneration.AMAZON_LINUX_2,
            edition=ec2.AmazonLinuxEdition.STANDARD,
            virtualization=ec2.AmazonLinuxVirt.HVM,
            storage=ec2.AmazonLinuxStorage.GENERAL_PURPOSE
            )

        # Create SecurityGroup
        security_group = ec2.SecurityGroup(
            self, "SecurityGroup",
            vpc=code_server_vpc,
            allow_all_outbound=True
        )
        
        security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(8080)
        )    

        # Create our EC2 instance running CodeServer
        code_server_instance = ec2.Instance(
            self, "CodeServerInstance",
            instance_type=ec2.InstanceType("t3.large"),
            machine_image=amzn_linux,
            vpc=code_server_vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=security_group,
            block_devices=[ec2.BlockDevice(device_name="/dev/xvda", volume=ec2.BlockDeviceVolume.ebs(20))]
        )

        # Add UserData
        code_server_instance.user_data.add_commands("mkdir -p ~/.local/lib ~/.local/bin ~/.config/code-server")
        code_server_instance.user_data.add_commands("curl -fL https://github.com/cdr/code-server/releases/download/v3.5.0/code-server-3.5.0-linux-amd64.tar.gz | tar -C ~/.local/lib -xz")
        code_server_instance.user_data.add_commands("mv ~/.local/lib/code-server-3.5.0-linux-amd64 ~/.local/lib/code-server-3.5.0")
        code_server_instance.user_data.add_commands("ln -s ~/.local/lib/code-server-3.5.0/bin/code-server ~/.local/bin/code-server")
        code_server_instance.user_data.add_commands("echo \"bind-addr: 0.0.0.0:8080\" > ~/.config/code-server/config.yaml")
        code_server_instance.user_data.add_commands("echo \"auth: password\" >> ~/.config/code-server/config.yaml")
        code_server_instance.user_data.add_commands("echo \"password: AWSServerless!\" >> ~/.config/code-server/config.yaml")
        code_server_instance.user_data.add_commands("echo \"cert: false\" >> ~/.config/code-server/config.yaml")
        code_server_instance.user_data.add_commands("~/.local/bin/code-server &")

        # Add ALB
        lb = elbv2.ApplicationLoadBalancer(
            self, "LB",
            vpc=code_server_vpc,
            internet_facing=True
        )
        listener = lb.add_listener("Listener", port=80)
        listener.connections.allow_default_port_from_any_ipv4("Open to the Internet")
        listener.connections.allow_to_any_ipv4(port_range=ec2.Port(string_representation="TCP 8080", protocol=ec2.Protocol.TCP, from_port=8080, to_port=8080))
        listener.add_targets("Target", port=8080, targets=[elbv2.InstanceTarget(
            instance_id=code_server_instance.instance_id,
            port=8080
        )])


app = core.App()
code_server_stack = CodeServerStack(app, "CodeServerStack")
app.synth()