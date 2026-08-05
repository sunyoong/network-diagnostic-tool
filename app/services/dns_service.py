"""DNS 조회 서비스.

dnspython의 비동기 리졸버(dns.asyncresolver)를 사용한다.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

import dns.asyncresolver
import dns.exception
import dns.rdatatype
import dns.resolver

SUPPORTED_TYPES = ("A", "AAAA", "CNAME", "MX", "TXT", "NS")


class DomainNotFoundError(Exception):
    pass


class NoRecordsError(Exception):
    """도메인은 존재하나 요청한 유형의 레코드가 없는 경우."""


@dataclass
class DnsLookupResult:
    domain: str
    record_type: str
    records: List[str]
    ttl: Optional[int]
    resolver: Optional[str]
    lookup_time_ms: int


def _format_record(record_type: str, rdata) -> str:
    if record_type == "MX":
        return f"{rdata.preference} {rdata.exchange.to_text().rstrip('.')}"
    if record_type == "TXT":
        return b"".join(rdata.strings).decode("utf-8", errors="replace")
    if record_type in ("CNAME", "NS"):
        return rdata.to_text().rstrip(".")
    return rdata.to_text()


async def perform_dns_lookup(domain: str, record_type: str) -> DnsLookupResult:
    resolver = dns.asyncresolver.Resolver()
    resolver_ip = resolver.nameservers[0] if resolver.nameservers else None

    start = time.monotonic()
    try:
        answer = await resolver.resolve(domain, record_type, raise_on_no_answer=True)
    except dns.resolver.NXDOMAIN as exc:
        raise DomainNotFoundError(f"도메인을 찾을 수 없습니다: {domain}") from exc
    except dns.resolver.NoAnswer as exc:
        raise NoRecordsError(
            f"{domain}에 {record_type} 레코드가 없습니다."
        ) from exc
    except dns.resolver.NoNameservers as exc:
        raise DomainNotFoundError(f"DNS 서버로부터 응답을 받지 못했습니다: {domain}") from exc
    except dns.exception.Timeout as exc:
        raise TimeoutError(f"DNS 조회 시간이 초과되었습니다: {domain}") from exc

    elapsed_ms = int((time.monotonic() - start) * 1000)

    records = [_format_record(record_type, rdata) for rdata in answer]
    ttl = answer.rrset.ttl if answer.rrset is not None else None

    return DnsLookupResult(
        domain=domain,
        record_type=record_type,
        records=records,
        ttl=ttl,
        resolver=resolver_ip,
        lookup_time_ms=elapsed_ms,
    )
