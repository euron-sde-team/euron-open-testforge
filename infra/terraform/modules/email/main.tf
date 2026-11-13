# Amazon SES for the mail TestForge sends: member notices (a person was added to a
# project). The api sends through SES (MAIL_BACKEND=ses) from `from_address`; its
# task role may send only as that address and only through this configuration set.
#
#   - a domain identity with Easy DKIM (three CNAMEs), published in Route53 when a zone is
#     given, otherwise listed in the dkim_records output for the operator to create
#   - a configuration set that records bounces and complaints as CloudWatch metrics, so a
#     spike of undeliverable notices shows up before it hurts the sender reputation
#   - new AWS accounts start in the SES sandbox: request production access before
#     notifying members outside verified addresses
resource "aws_sesv2_email_identity" "this" {
  email_identity         = var.domain
  configuration_set_name = aws_sesv2_configuration_set.this.configuration_set_name
}

resource "aws_sesv2_configuration_set" "this" {
  configuration_set_name = "${var.name_prefix}-mail"

  delivery_options {
    tls_policy = "REQUIRE"
  }
  reputation_options {
    reputation_metrics_enabled = true
  }
  sending_options {
    sending_enabled = true
  }
  suppression_options {
    suppressed_reasons = ["BOUNCE", "COMPLAINT"]
  }
}

resource "aws_sesv2_configuration_set_event_destination" "metrics" {
  configuration_set_name = aws_sesv2_configuration_set.this.configuration_set_name
  event_destination_name = "cloudwatch"
  event_destination {
    enabled              = true
    matching_event_types = ["SEND", "BOUNCE", "COMPLAINT", "REJECT", "DELIVERY"]
    cloud_watch_destination {
      dimension_configuration {
        default_dimension_value = "testforge"
        dimension_name          = "app"
        dimension_value_source  = "MESSAGE_TAG"
      }
    }
  }
}

resource "aws_route53_record" "dkim" {
  count   = var.route53_zone_id == null ? 0 : 3
  zone_id = var.route53_zone_id
  name    = "${aws_sesv2_email_identity.this.dkim_signing_attributes[0].tokens[count.index]}._domainkey.${var.domain}"
  type    = "CNAME"
  ttl     = 600
  records = ["${aws_sesv2_email_identity.this.dkim_signing_attributes[0].tokens[count.index]}.dkim.amazonses.com"]
}

data "aws_iam_policy_document" "send" {
  statement {
    sid     = "SendNotices"
    actions = ["ses:SendEmail", "ses:SendRawEmail"]
    resources = [
      aws_sesv2_email_identity.this.arn,
      aws_sesv2_configuration_set.this.arn,
    ]
    condition {
      test     = "StringEquals"
      variable = "ses:FromAddress"
      values   = [var.from_address]
    }
  }
}
