resource "aws_lb" "main" {
  name               = "${var.project_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  tags = {
    Name        = "${var.project_name}-alb"
    Environment = var.environment
  }
}

resource "aws_lb_target_group" "web" {
  name        = "${var.project_name}-tg-web"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/"
    matcher             = "200-399"
    healthy_threshold   = 2
    unhealthy_threshold = 10
  }
}

resource "aws_lb_target_group" "api" {
  name        = "${var.project_name}-tg-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 10
  }
}

# ─── Active: HTTP listener on port 80 ────────────────────────────────────────
# CloudFront sits in front of the ALB and handles TLS from the user's browser.
# The CloudFront → ALB hop stays on HTTP inside the private VPC — this is fine.
# When you get a custom domain + ACM cert, replace this listener with the
# http_redirect + https listeners below (they are commented out for now).
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }

  condition {
    path_pattern {
      values = ["/v1/*", "/admin/*", "/health", "/docs", "/openapi.json"]
    }
  }
}

# ─── TODO (custom domain): Uncomment the two blocks below once you have: ─────
#   1. A custom domain (e.g. app.yourbusiness.com)
#   2. An ACM certificate issued in ap-south-1 for that domain
#   3. Set acm_certificate_arn in terraform.tfvars
#   4. Remove the "http" listener + rule above and apply this instead.
#
# ─── Task 6: TLS 1.3 only — HTTP → HTTPS redirect on port 80 ─────────────────
# PRD §11.1 requires TLS 1.3. Default ALB policy (ELBSecurityPolicy-2016-08)
# allows TLS 1.2 — the HTTPS listener below replaces it with TLS13-only.
#
# resource "aws_lb_listener" "http_redirect" {
#   load_balancer_arn = aws_lb.main.arn
#   port              = "80"
#   protocol          = "HTTP"
#
#   default_action {
#     type = "redirect"
#     redirect {
#       port        = "443"
#       protocol    = "HTTPS"
#       status_code = "HTTP_301"
#     }
#   }
# }
#
# resource "aws_lb_listener" "https" {
#   load_balancer_arn = aws_lb.main.arn
#   port              = "443"
#   protocol          = "HTTPS"
#
#   # ELBSecurityPolicy-TLS13-1-3-2021-06 — TLS 1.3 ONLY (no TLS 1.2 fallback)
#   # Reference: https://docs.aws.amazon.com/elasticloadbalancing/latest/application/
#   #            create-https-listener.html#describe-ssl-policies
#   ssl_policy      = "ELBSecurityPolicy-TLS13-1-3-2021-06"
#   certificate_arn = var.acm_certificate_arn
#
#   default_action {
#     type             = "forward"
#     target_group_arn = aws_lb_target_group.web.arn
#   }
# }
#
# resource "aws_lb_listener_rule" "api_https" {
#   listener_arn = aws_lb_listener.https.arn
#   priority     = 100
#
#   action {
#     type             = "forward"
#     target_group_arn = aws_lb_target_group.api.arn
#   }
#
#   condition {
#     path_pattern {
#       values = ["/v1/*", "/admin/*", "/health", "/docs", "/openapi.json"]
#     }
#   }
# }
