
{-# language MagicHash #-}
{-# language BangPatterns #-}
{-# language ScopedTypeVariables #-}
-- {-# options -fregs-graph #-}


module M where

import GHC.CString
import GHC.Exts

check :: Char# -> Char# -> Addr# -> Bool
check c ch addr
  | isTrue# (ch `eqChar#` '\0'#) = False
  | isTrue# (ch `eqChar#` c    ) = True
  | True                         =
      let !addr' = (addr `plusAddr#` 1#)
          !ch' = indexCharOffAddr# addr' 0#
      in check c ch' addr'
