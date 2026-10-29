# Experimental demo quote-timing correction

The Xtreme Android V5 reported 'Ultimo tick: 0s' plus 'Preco ausente ou atrasado'.
The original broker has TWO checks: local arrival age and raw source timestamp
age. A steady source clock offset can fail the second even when quotes are live.

This experimental change retains the local <=2-second arrival constraint,
requires progressing source timestamps across separate received packets when
the clocks differ by more than 3 seconds, and rejects absurd >12-hour offsets.
It cannot by itself prove the broker will accept a five-second demo order.
Auto mode still requires an official settled five-second manual demo trade.
No Pocket Option credentials, SSIDs or order payloads are logged or saved.
Deploy separately only after tests and informed review.
