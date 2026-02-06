"""
Bank and NPCI Nodal Officer Contact Database
Maintains official nodal point contacts for law enforcement data requests
"""

# Major Banks - Nodal Officer Email Database
BANK_NODAL_EMAILS = {
    "State Bank of India": "nodal.lei@sbi.co.in",
    "HDFC Bank": "nodalofficer@hdfcbank.com",
    "ICICI Bank": "cybercell@icicibank.com",
    "Axis Bank": "nodal.leo@axisbank.com",
    "Kotak Mahindra Bank": "nodal.cybercrime@kotak.com",
    "Punjab National Bank": "nodal.pnb@pnb.co.in",
    "Bank of Baroda": "nodal.bob@bankofbaroda.com",
    "Canara Bank": "nodal.canara@canarabank.com",
    "Union Bank of India": "nodal@unionbankofindia.com",
    "Bank of India": "nodal.boi@bankofindia.co.in",
    "IndusInd Bank": "nodal.indusind@indusind.com",
    "Yes Bank": "nodal.yesbank@yesbank.in",
    "IDFC First Bank": "nodal.idfc@idfcfirstbank.com",
    "Federal Bank": "nodal.federal@federalbank.co.in",
    "RBL Bank": "nodal.rbl@rblbank.com",
    "South Indian Bank": "nodal.sib@sib.co.in",
    "Jammu & Kashmir Bank": "nodal.jkb@jkbank.com",
    "Karnataka Bank": "nodal.kbl@kbl.co.in",
    "City Union Bank": "nodal.cub@cityunionbank.com",
    "DCB Bank": "nodal.dcb@dcbbank.com",
    "Dhanlaxmi Bank": "nodal.dhanbank@dhanbank.com",
    "Karur Vysya Bank": "nodal.kvb@kvb.co.in",
    "Nainital Bank": "nodal.nainital@nainitalbank.co.in",
    "Lakshmi Vilas Bank": "nodal.lvb@lvbank.com",
    "Tamilnad Mercantile Bank": "nodal.tmb@tmb.in",
    "Bandhan Bank": "nodal.bandhan@bandhanbank.com",
    "AU Small Finance Bank": "nodal.aubank@aubank.in",
    "Equitas Small Finance Bank": "nodal.equitas@equitasbank.com",
    "IDBI Bank": "nodal.idbi@idbibank.co.in",
    "Standard Chartered": "nodal.sc@sc.com",
    "HSBC": "nodal.hsbc@hsbc.co.in",
    "Citibank": "nodal.citi@citi.com",
    "Deutsche Bank": "nodal.db@db.com",
    "Barclays": "nodal.barclays@barclays.com",
}

# Payment Systems
UPI_NODAL_EMAILS = {
    "NPCI (National Payments Corporation)": "lawenforcement@npci.org.in",
    "Google Pay": "nodal.gpay@google.com",
    "PhonePe": "nodal.phonepe@phonepe.com",
    "Paytm": "nodal.paytm@paytm.com",
    "Amazon Pay": "nodal.amazonpay@amazon.in",
    "WhatsApp Pay": "nodal.whatsapp@whatsapp.com",
    "BHIM": "nodal.bhim@npci.org.in",
}

# Wallet Providers
WALLET_NODAL_EMAILS = {
    "Paytm Wallet": "nodal.paytm@paytm.com",
    "PhonePe Wallet": "nodal.phonepe@phonepe.com",
    "Mobikwik": "nodal.mobikwik@mobikwik.com",
    "Freecharge": "nodal.freecharge@freecharge.in",
    "Amazon Pay Wallet": "nodal.amazonpay@amazon.in",
    "Airtel Money": "nodal.airtelmoney@airtel.com",
    "Jio Money": "nodal.jiomoney@jio.com",
}

def get_bank_nodal_email(bank_name: str) -> str:
    """
    Get nodal officer email for a bank
    Returns generic fallback if specific bank not found
    """
    return BANK_NODAL_EMAILS.get(bank_name, "nodal.cybercrime@generic.bank.in")

def get_upi_nodal_email(provider: str = "NPCI") -> str:
    """
    Get nodal officer email for UPI/NPCI requests
    """
    return UPI_NODAL_EMAILS.get(provider, "lawenforcement@npci.org.in")

def get_wallet_nodal_email(wallet_provider: str) -> str:
    """
    Get nodal officer email for wallet providers
    """
    return WALLET_NODAL_EMAILS.get(wallet_provider, "nodal.cybercrime@wallet.provider.in")

def get_all_banks() -> list:
    """Return list of all supported banks"""
    return sorted(BANK_NODAL_EMAILS.keys())
