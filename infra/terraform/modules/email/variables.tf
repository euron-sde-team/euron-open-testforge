variable "name_prefix" {
  description = "Prefix for every resource name."
  type        = string
}

variable "domain" {
  description = "Domain mail is sent from (an SES domain identity), e.g. testforge.example.com."
  type        = string
}

variable "from_address" {
  description = "The only From address the api may send as, e.g. no-reply@testforge.example.com."
  type        = string
  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+$", var.from_address))
    error_message = "from_address must be an email address."
  }
}

variable "route53_zone_id" {
  description = "Hosted zone that receives the DKIM records. Null: create them yourself (dkim_records output)."
  type        = string
  default     = null
}
