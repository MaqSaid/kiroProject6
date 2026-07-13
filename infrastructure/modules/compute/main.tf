variable "project_name" { type = string; default = "rag-pipeline" }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "security_group_id" { type = string }
variable "container_image" { type = string }
variable "cpu" { type = number; default = 1024 }
variable "memory" { type = number; default = 2048 }
variable "desired_count" { type = number; default = 2 }

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-${var.environment}"
  setting { name = "containerInsights"; value = "enabled" }
  tags = { Project = var.project_name, Environment = var.environment, ManagedBy = "terraform" }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project_name}-${var.environment}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "api"
    image = var.container_image
    portMappings = [{ containerPort = 8080, protocol = "tcp" }]
    environment = [
      { name = "RAG_AGENT_REGION", value = "us-east-1" },
      { name = "RAG_AGENT_TIER", value = "pro" },
    ]
    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import httpx; assert httpx.get('http://localhost:8080/health',timeout=5).status_code==200\""]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 60
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = { "awslogs-group" = "/ecs/${var.project_name}-${var.environment}", "awslogs-region" = "us-east-1", "awslogs-stream-prefix" = "api" }
    }
  }])
}

resource "aws_ecs_service" "api" {
  name            = "${var.project_name}-${var.environment}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  network_configuration { subnets = var.subnet_ids; security_groups = [var.security_group_id]; assign_public_ip = true }
  load_balancer { target_group_arn = aws_lb_target_group.api.arn; container_name = "api"; container_port = 8080 }
}

resource "aws_lb" "api" {
  name               = "${var.project_name}-${var.environment}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.security_group_id]
  subnets            = var.subnet_ids
  tags = { Project = var.project_name, Environment = var.environment, ManagedBy = "terraform" }
}

resource "aws_lb_target_group" "api" {
  name        = "${var.project_name}-${var.environment}-tg"
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"
  health_check { path = "/health"; interval = 30; timeout = 10 }
}

resource "aws_lb_listener" "api" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"
  default_action { type = "forward"; target_group_arn = aws_lb_target_group.api.arn }
}

resource "aws_appautoscaling_target" "api" {
  max_capacity       = 10
  min_capacity       = var.desired_count
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "cpu" {
  name               = "${var.project_name}-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  service_namespace  = aws_appautoscaling_target.api.service_namespace
  target_tracking_scaling_policy_configuration {
    predefined_metric_specification { predefined_metric_type = "ECSServiceAverageCPUUtilization" }
    target_value = 70.0
  }
}

resource "aws_iam_role" "ecs_execution" {
  name               = "${var.project_name}-${var.environment}-ecs-exec"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" } }] })
}

resource "aws_iam_role" "ecs_task" {
  name               = "${var.project_name}-${var.environment}-ecs-task"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" } }] })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "bedrock_access" {
  name   = "bedrock-access"
  role   = aws_iam_role.ecs_task.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"], Resource = "*" }] })
}

output "alb_dns_name" { value = aws_lb.api.dns_name }
output "cluster_name" { value = aws_ecs_cluster.main.name }
